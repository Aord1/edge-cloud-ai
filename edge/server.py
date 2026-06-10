"""边缘端 HTTP 服务器 — MJPEG 流 + REST API，供 Web 端控制检测。

用法:
    server = EdgeServer(host="0.0.0.0", port=8080)
    server.start()
    # Web 端调用 POST /api/configure → POST /api/start
    ...

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

import json
import os
import threading
import time
import uuid
from collections import deque
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import cv2
import numpy as np

from .capture.camera import make_camera
from .classify.alert import AlertEngine
from .classify.decision import Action, classify
from .config import edge_settings
from .inference.detector import CLASS_COLORS, YOLODetector
from .network.http_client import upload_sync
from .tracking import DefectTracker


# ── HTTP Handler ────────────────────────────────────────────────

class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/stream":
            self._serve_mjpeg()
        elif self.path == "/api/status":
            self._json(self.server._owner.get_status())
        elif self.path == "/api/summary":
            self._json(self.server._owner.get_summary())
        elif self.path == "/api/files":
            self._json(self.server._owner.list_files())
        elif self.path == "/api/cameras":
            self._json(self.server._owner.list_cameras())
        else:
            self.send_error(404)

    def do_POST(self) -> None:
        owner: EdgeServer = self.server._owner
        content_type = self.headers.get("Content-Type", "")
        if self.path == "/api/upload-file" and "multipart" in content_type:
            fname, body = self._parse_multipart()
            result = owner.upload_file(fname, body)
            self._json(result)
        else:
            body = self._read_body()
            if self.path == "/api/configure":
                owner.configure(**body)
                self._json({"ok": True, "source": owner._source})
            elif self.path == "/api/start":
                result = owner.start_detection()
                self._json(result)
            elif self.path == "/api/stop":
                result = owner.stop_detection()
                self._json(result)
            else:
                self.send_error(404)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._cors_headers()
        self.end_headers()

    # ── helpers ──

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length > 0 else b"{}"
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            self._json({"ok": False, "error": "请求体 JSON 解析失败"})
            return {}

    def _json(self, data: dict) -> None:
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self._cors_headers()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _parse_multipart(self) -> tuple[str, bytes]:
        """从 multipart/form-data 中提取第一个文件的文件名和内容。"""
        import email.parser
        content_type = self.headers.get("Content-Type", "")
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        boundary = content_type.split("boundary=")[1].encode()
        parts = raw.split(b"--" + boundary)
        for part in parts:
            if b"Content-Disposition" not in part:
                continue
            if b"filename=" not in part:
                continue
            # 提取原始文件名
            header, _, _ = part.partition(b"\r\n\r\n")
            fname = "upload"
            for line in header.split(b"\r\n"):
                if b"filename=" in line:
                    # 形如: Content-Disposition: form-data; name="file"; filename="test.avi"
                    raw_fname = line.split(b'filename="')[-1].split(b'"')[0].decode("utf-8", "ignore")
                    fname = raw_fname.strip()
                    break
            header_end = part.find(b"\r\n\r\n")
            body = part[header_end + 4:]
            if body.endswith(b"\r\n"):
                body = body[:-2]
            return fname, body
        return "upload", b""

    def _serve_mjpeg(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Connection", "close")
        self.end_headers()
        owner: EdgeServer = self.server._owner
        while owner._stream_running:
            frame = owner._pop_frame(timeout=edge_settings.mjpeg_frame_timeout)
            if frame is None:
                continue
            _, jpg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, edge_settings.mjpeg_quality])
            try:
                self.wfile.write(b"--frame\r\n")
                self.wfile.write(b"Content-Type: image/jpeg\r\n")
                self.wfile.write(f"Content-Length: {len(jpg)}\r\n\r\n".encode())
                self.wfile.write(jpg.tobytes())
                self.wfile.write(b"\r\n")
            except (BrokenPipeError, ConnectionResetError):
                break

    def log_message(self, format, *args) -> None:
        pass


# ── Server ──────────────────────────────────────────────────────

class EdgeServer:
    """HTTP 服务器 + 检测控制器。"""

    def __init__(self, host: str | None = None, port: int | None = None) -> None:
        self._host = host if host is not None else edge_settings.server_host
        self._port = port if port is not None else edge_settings.server_port
        self._http: HTTPServer | None = None
        self._http_thread: threading.Thread | None = None

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
        self._frame: np.ndarray | None = None
        self._lock = threading.Lock()
        self._cond = threading.Condition(self._lock)
        self._stream_running = True

        # 状态 & 汇总
        self._status: dict = {"state": "idle", "detections": [], "count": 0, "fps": 0.0}
        self._records: list[dict] = []
        self._edge_count = 0
        self._cloud_count = 0
        self._tracker = DefectTracker(iou_threshold=0.3, min_frames=1)

    # ── 生命周期 ──

    def start(self) -> None:
        self._http = HTTPServer((self._host, self._port), _Handler)
        self._http._owner = self
        self._http_thread = threading.Thread(target=self._http.serve_forever, daemon=True)
        self._http_thread.start()
        print(f"[EdgeServer] http://{self._host}:{self._port}  (stream /api/*)")

    def stop(self) -> None:
        self.stop_detection()
        self._stream_running = False
        if self._http:
            self._http.shutdown()
        if self._http_thread:
            self._http_thread.join(timeout=edge_settings.server_thread_join_timeout)
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
        """保存上传的视频/图片文件到 video_dir，保留原始扩展名。"""
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
        # 不阻塞 HTTP 响应，后台等待检测线程退出
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
        with self._lock:
            self._frame = frame.copy()
            self._cond.notify_all()

    def _pop_frame(self, timeout: float = 1.0) -> np.ndarray | None:
        with self._lock:
            if self._frame is None:
                self._cond.wait(timeout)
            frame, self._frame = self._frame, None
            return frame

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

                # 本地告警
                if decision.action == Action.EDGE and decision.local:
                    alert = alerter.evaluate(decision.local)
                    if alert:
                        self._edge_count += 1

                # 上传云端（经 tracker 去重：同一缺陷只上传一次）
                if decision.action == Action.CLOUD:
                    new_defects = self._tracker.update(decision.upload)
                    if new_defects:
                        _, jpg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, edge_settings.upload_jpeg_quality])
                        try:
                            r = upload_sync(
                                self._api_url, self._device_id,
                                new_defects, decision.reason,
                                result.avg_confidence, result.inference_ms, result.timestamp,
                                frame_jpg=bytes(jpg),
                            )
                            cloud_id = r.get("id", "")
                            self._cloud_count += 1
                            names = ", ".join(d["class_name"] for d in new_defects)
                            print(f"  [上传云端] {names} ({len(new_defects)}/{len(decision.upload)}个新缺陷) → {r.get('message', 'ok')}")
                        except Exception as e:
                            cloud_id = ""
                            print(f"  [上传失败] {e}")

                    # 记录（供 Web 端查看）
                    if result.count:
                        self._records.append({
                            "time": time.strftime("%H:%M:%S"),
                            "defect_types": [d.class_name for d in result.detections],
                            "avg_confidence": round(result.avg_confidence, 3),
                            "reason": decision.reason,
                            "decision": "CLOUD",
                            "cloud_id": cloud_id,
                            "count": result.count,
                        })
                elif result.count:
                    self._records.append({
                        "time": time.strftime("%H:%M:%S"),
                        "defect_types": [d.class_name for d in result.detections],
                        "avg_confidence": round(result.avg_confidence, 3),
                        "reason": decision.reason,
                        "decision": "EDGE",
                        "cloud_id": "",
                        "count": result.count,
                    })

                # 生成 MJPEG 帧（960px 宽）
                h, w = frame.shape[:2]
                web_w = edge_settings.mjpeg_stream_width
                if w > web_w:
                    ws = web_w / w
                    web_frame = cv2.resize(frame, (web_w, int(h * ws)))
                    annotated = _annotate_scaled(web_frame, result, decision, ws, ws, actual_fps)
                else:
                    annotated = _annotate(frame, result, decision, actual_fps)
                self._push_frame(annotated)

                # 更新状态
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
    cv2.putText(frame, status, (10, frame.shape[0] - 14),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
    return frame
