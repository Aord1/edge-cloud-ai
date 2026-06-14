"""边缘端 FastAPI 服务器 — MJPEG 流 + REST API，供 Web 端控制检测。

用法:
    server = EdgeServer(host="0.0.0.0", port=8080)
    server.start()
    # Web 端调用 POST /api/configure → POST /api/start

端点:
    GET  /stream          MJPEG 视频流
    GET  /api/status      当前检测状态
    GET  /api/files       视频目录文件列表
    GET  /api/cameras     可用摄像头列表
    POST /api/configure   设置检测参数
    POST /api/upload-file 上传视频文件
    POST /api/start       开启检测
    POST /api/stop        停止检测
    GET  /api/summary     检测结束后返回汇总
"""


from __future__ import annotations

import asyncio
import os
import threading
import time
import uuid
from collections import deque
from pathlib import Path

import cv2
import numpy as np
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
import uvicorn

from .capture.camera import make_camera
from .classify.alert import AlertEngine
from .classify.decision import Action, classify
from .config import edge_settings
from .inference.detector import CLASS_COLORS, YOLODetector
from .inference.visual import put_chinese_text
from .network.http_client import upload_sync
from .network.mqtt_client import EdgeMQTTClient
from .tracking import DefectTracker


# ── FastAPI App ──────────────────────────────────────────────────

app = FastAPI(title="Edge Server", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_server: EdgeServer | None = None


def _get_server() -> EdgeServer:
    if _server is None:
        raise HTTPException(status_code=503, detail="Edge Server 未初始化")
    return _server


# ── MJPEG 流 ─────────────────────────────────────────────────────

async def _generate_mjpeg():
    server = _get_server()
    while server._stream_running:
        frame = server._latest_frame
        if frame is None:
            await asyncio.sleep(0.05)
            continue
        _, jpg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, edge_settings.mjpeg_quality])
        yield (b"--frame\r\n"
               b"Content-Type: image/jpeg\r\n"
               b"Content-Length: " + str(len(jpg)).encode() + b"\r\n\r\n"
               + jpg.tobytes() + b"\r\n")
        await asyncio.sleep(0.02)


@app.get("/stream")
async def stream():
    return StreamingResponse(
        _generate_mjpeg(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-cache", "Connection": "close"},
    )


# ── REST API ─────────────────────────────────────────────────────

@app.get("/api/status")
async def api_status():
    return _get_server().get_status()


@app.get("/api/summary")
async def api_summary():
    return _get_server().get_summary()


@app.get("/api/files")
async def api_files():
    return _get_server().list_files()


@app.get("/api/cameras")
async def api_cameras():
    return _get_server().list_cameras()


@app.post("/api/configure")
async def api_configure(
    source: str = Form(default="0"),
    conf: float = Form(default=None),
    conf_edge: float = Form(default=None),
    api_url: str = Form(default=""),
    device_id: str = Form(default=""),
    video_dir: str = Form(default=""),
):
    server = _get_server()
    server.configure(
        source=source,
        conf=conf if conf is not None else edge_settings.detection_conf_threshold,
        conf_edge=conf_edge if conf_edge is not None else edge_settings.detection_conf_edge,
        api_url=api_url,
        device_id=device_id,
        video_dir=video_dir,
    )
    return {"ok": True, "source": server._source}


@app.post("/api/upload-file", status_code=201)
async def api_upload_file(file: UploadFile = File(...)):
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="未收到文件")
    result = _get_server().upload_file(file.filename or "upload", data)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error", "上传失败"))
    return result


@app.post("/api/start")
async def api_start():
    result = _get_server().start_detection()
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error", "启动失败"))
    return result


@app.post("/api/stop")
async def api_stop():
    return _get_server().stop_detection()


# ── 边缘检测服务 ──────────────────────────────────────────────────

class EdgeServer:
    """检测控制器 + MJPEG 帧管理。FastAPI 路由调用此类方法。"""

    def __init__(self, host: str | None = None, port: int | None = None) -> None:
        global _server
        _server = self

        self._host = host if host is not None else edge_settings.server_host
        self._port = port if port is not None else edge_settings.server_port
        self._mqtt: EdgeMQTTClient | None = None

        # 配置（Web 端通过 /api/configure 设置）
        self._source: str = "0"
        self._conf: float = edge_settings.detection_conf_threshold
        self._conf_edge: float = edge_settings.detection_conf_edge
        self._api_url: str = edge_settings.edge_cloud_api_url
        self._device_id: str = edge_settings.edge_device_id
        self._video_dir: str = str(
            Path(__file__).resolve().parent / "uploads"
        ).replace("\\", "/")

        # 检测线程
        self._detect_running = False
        self._detect_thread: threading.Thread | None = None
        self._detect_started = False

        # MJPEG 帧
        self._latest_frame: np.ndarray | None = None
        self._stream_running = True

        # 状态 & 汇总
        self._status: dict = {"state": "idle", "detections": [], "count": 0, "fps": 0.0}
        self._records: list[dict] = []
        self._edge_count = 0
        self._cloud_count = 0
        self._tracker = DefectTracker(iou_threshold=0.3, min_frames=1)

    # ── 生命周期 ──

    def start(self) -> None:
        self._mqtt = EdgeMQTTClient()
        if self._mqtt.connect():
            print(f"[EdgeServer] MQTT 已连接 {edge_settings.mqtt_broker_host}:{edge_settings.mqtt_broker_port}")
        else:
            print("[EdgeServer] MQTT 连接失败，将回退到 HTTP")
            self._mqtt = None

        config = uvicorn.Config(
            app, host=self._host, port=self._port, log_level="warning",
        )
        server = uvicorn.Server(config)
        threading.Thread(target=server.run, daemon=True).start()
        print(f"[EdgeServer] http://{self._host}:{self._port}  (stream /api/*)")

    def stop(self) -> None:
        self.stop_detection()
        self._stream_running = False
        if self._mqtt:
            self._mqtt.disconnect()
            self._mqtt = None
        print("[EdgeServer] 已停止")

    # ── API: 配置 ──

    def configure(self, source: str = "0",
                  conf: float | None = None,
                  conf_edge: float | None = None,
                  api_url: str = "",
                  device_id: str = "", video_dir: str = "") -> None:
        self._source = source
        self._conf = conf if conf is not None else edge_settings.detection_conf_threshold
        self._conf_edge = conf_edge if conf_edge is not None else edge_settings.detection_conf_edge
        if api_url:
            self._api_url = api_url
        if device_id:
            self._device_id = device_id
        if video_dir:
            self._video_dir = video_dir
        print(f"[EdgeServer] 配置 source={source} conf={conf} conf_edge={conf_edge}")

    # ── API: 文件 / 摄像头 ──

    def list_files(self) -> dict:
        d = self._video_dir or "."
        try:
            entries = []
            for name in sorted(os.listdir(d)):
                path = os.path.join(d, name)
                if os.path.isfile(path) and name.lower().endswith(
                    (".mp4", ".avi", ".mov", ".mkv", ".flv", ".wmv", ".webm", ".jpg", ".png", ".bmp")
                ):
                    size_mb = os.path.getsize(path) / (1024 * 1024)
                    entries.append({"name": name, "path": path, "size_mb": round(size_mb, 1)})
            return {"dir": os.path.abspath(d), "files": entries}
        except Exception as e:
            return {"dir": os.path.abspath(d), "files": [], "error": str(e)}

    def list_cameras(self) -> dict:
        import io, sys
        available = []
        for idx in range(edge_settings.camera_probe_max):
            old_stderr = sys.stderr
            sys.stderr = io.StringIO()
            try:
                cap = cv2.VideoCapture(idx)
            finally:
                sys.stderr = old_stderr
            if cap.isOpened():
                available.append(idx)
            cap.release()
        return {"cameras": available, "max_probed": edge_settings.camera_probe_max - 1}

    def upload_file(self, original_name: str, data: bytes) -> dict:
        if not data:
            return {"ok": False, "error": "未收到文件"}
        d = self._video_dir or "."
        os.makedirs(d, exist_ok=True)
        ext = Path(original_name).suffix or ".mp4"
        fname = f"upload_{uuid.uuid4().hex[:8]}{ext}"
        fpath = os.path.join(d, fname)
        with open(fpath, "wb") as f:
            f.write(data)
        size_mb = os.path.getsize(fpath) / (1024 * 1024)
        print(f"[EdgeServer] 文件已上传: {fpath} ({size_mb:.1f}MB)")
        return {"ok": True, "path": os.path.abspath(fpath), "name": fname,
                "size_mb": round(size_mb, 1)}

    # ── API: 控制 ──

    def start_detection(self) -> dict:
        if self._detect_running:
            return {"ok": False, "error": "检测已在运行"}
        self._detect_running = True
        self._detect_started = True
        self._records.clear()
        self._edge_count = 0
        self._cloud_count = 0
        self._tracker.reset()
        self._status["state"] = "running"
        self._detect_thread = threading.Thread(target=self._detection_loop, daemon=True)
        self._detect_thread.start()
        print(f"[EdgeServer] 检测启动 source={self._source}")
        return {"ok": True, "status": "started", "source": self._source}

    def stop_detection(self) -> dict:
        if not self._detect_running:
            return {"ok": False, "error": "检测未在运行"}
        self._detect_running = False
        self._status["state"] = "stopping"
        dt = self._detect_thread
        if dt and dt.is_alive():
            threading.Thread(target=dt.join, daemon=True).start()
        print(f"[EdgeServer] 检测停止中 edge={self._edge_count} cloud={self._cloud_count}")
        return {"ok": True, "status": "stopping",
                "edge_count": self._edge_count, "cloud_count": self._cloud_count}

    # ── 查询 ──

    def get_status(self) -> dict:
        return self._status

    def get_summary(self) -> dict:
        return {
            "total": len(self._records),
            "cloud_count": self._cloud_count,
            "edge_count": self._edge_count,
            "records": self._records,
        }

    # ── 帧推送 ──

    def _push_frame(self, frame: np.ndarray) -> None:
        self._latest_frame = frame.copy()

    # ── 检测主循环（后台线程） ──

    def _detection_loop(self) -> None:
        src = int(self._source) if str(self._source).lstrip("-").isdigit() else self._source
        cam = make_camera(source=src, fps=0)
        detector = YOLODetector(
            model_path=edge_settings.model_path,
            conf_threshold=self._conf,
            max_detections=edge_settings.detection_max_detections,
        )
        alerter = AlertEngine()
        fps_window: deque[float] = deque(maxlen=edge_settings.fps_window_size)

        cam.open()
        try:
            while self._detect_running:
                t0 = time.perf_counter()
                frame = cam.read()
                if frame is None:
                    break

                result = detector.detect(frame)
                decision = classify(result, conf_edge=self._conf_edge)

                elapsed = time.perf_counter() - t0
                fps_window.append(1.0 / max(elapsed, 0.001))
                actual_fps = sum(fps_window) / len(fps_window)

                if decision.action == Action.EDGE and decision.local:
                    alert = alerter.evaluate(decision.local)
                    if alert:
                        self._edge_count += 1

                dets_to_upload = decision.upload if decision.action == Action.CLOUD else decision.local
                dec_str = "CLOUD" if decision.action == Action.CLOUD else "EDGE"

                if dets_to_upload:
                    new_defects = self._tracker.update(dets_to_upload)
                    if new_defects:
                        _, jpg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, edge_settings.upload_jpeg_quality])
                        jpg_bytes = bytes(jpg)
                        cloud_id = ""

                        if self._mqtt and self._mqtt.connected:
                            ok = self._mqtt.publish_defect(
                                new_defects, decision.reason,
                                result.avg_confidence, result.inference_ms, result.timestamp,
                                frame_jpg=jpg_bytes, decision=dec_str,
                            )
                            if ok:
                                self._cloud_count += 1 if dec_str == "CLOUD" else 0
                                self._edge_count += 1 if dec_str == "EDGE" else 0
                                names = ", ".join(d["class_name"] for d in new_defects)
                                print(f"  [MQTT上传] [{dec_str}] {decision.summary} ({len(new_defects)}个新缺陷)")
                            else:
                                print(f"  [MQTT上传失败]")
                        else:
                            try:
                                r = upload_sync(
                                    self._api_url, self._device_id,
                                    new_defects, decision.reason,
                                    result.avg_confidence, result.inference_ms, result.timestamp,
                                    frame_jpg=jpg_bytes, decision=dec_str,
                                )
                                cloud_id = r.get("id", "")
                                self._cloud_count += 1 if dec_str == "CLOUD" else 0
                                self._edge_count += 1 if dec_str == "EDGE" else 0
                                names = ", ".join(d["class_name"] for d in new_defects)
                                print(f"  [HTTP上传] [{dec_str}] {names} ({len(new_defects)}个新缺陷) → {r.get('message', 'ok')}")
                            except Exception as e:
                                cloud_id = ""
                                print(f"  [上传失败] {e}")

                    if result.count:
                        self._records.append({
                            "time": time.strftime("%H:%M:%S"),
                            "defect_types": [d.class_name for d in result.detections],
                            "avg_confidence": round(result.avg_confidence, 3),
                            "reason": decision.reason,
                            "decision": dec_str,
                            "cloud_id": cloud_id,
                            "count": result.count,
                        })

                h, w = frame.shape[:2]
                web_w = edge_settings.mjpeg_stream_width
                if w > web_w:
                    ws = web_w / w
                    web_frame = cv2.resize(frame, (web_w, int(h * ws)))
                    annotated = _annotate_scaled(web_frame, result, decision, ws, ws, actual_fps)
                else:
                    annotated = _annotate(frame, result, decision, actual_fps)
                self._push_frame(annotated)

                self._status.update({
                    "detections": [
                        {"class": d.class_name, "conf": d.confidence, "bbox": list(d.bbox)}
                        for d in result.detections
                    ],
                    "count": result.count,
                    "fps": round(actual_fps, 1),
                    "inference_ms": result.inference_ms,
                    "decision": "CLOUD" if decision.action == Action.CLOUD else "EDGE",
                    "reason": decision.reason,
                    "state": "running",
                })
        finally:
            cam.close()
            self._detect_running = False
            self._status["state"] = "stopped"


# ── 标注 ────────────────────────────────────────────────────────

def _annotate(frame: np.ndarray, result, decision, fps: float) -> np.ndarray:
    return _draw_frame(frame.copy(), result, decision, fps, 1.0, 1.0)


def _annotate_scaled(frame: np.ndarray, result, decision,
                     sx: float, sy: float, fps: float) -> np.ndarray:
    return _draw_frame(frame.copy(), result, decision, fps, sx, sy)


def _draw_frame(frame: np.ndarray, result, decision,
                fps: float, sx: float, sy: float) -> np.ndarray:
    for d in result.detections:
        c = CLASS_COLORS.get(d.class_id, (0, 255, 0))
        x1, y1 = int(d.x1 * sx), int(d.y1 * sy)
        x2, y2 = int(d.x2 * sx), int(d.y2 * sy)
        cv2.rectangle(frame, (x1, y1), (x2, y2), c, 2)
        label = f"{d.class_name} {d.confidence:.2f}"
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)
        cv2.rectangle(frame, (x1, y1 - th - 4), (x1 + tw + 4, y1), c, -1)
        cv2.putText(frame, label, (x1 + 2, y1 - 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 2)
    status = f"FPS:{fps:.0f} | 缺陷:{result.count} | "
    status += "EDGE" if decision.action == Action.EDGE else ">>CLOUD"
    color = (0, 255, 0) if decision.action == Action.EDGE else (0, 0, 255)
    put_chinese_text(frame, status, (10, frame.shape[0] - 32), font_size=20, color=color)
    return frame


def main() -> None:
    """命令行入口：python -m edge.server"""
    server = EdgeServer()
    server.configure(source="0")
    server.start()
    print("[EdgeServer] 按 Ctrl+C 退出")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        server.stop()


if __name__ == "__main__":
    main()