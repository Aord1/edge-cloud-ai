"""边缘端检测服务 — EdgeServer 业务逻辑，与 HTTP 层解耦。

由 edge/server.py 创建 FastAPI 应用时初始化，
由 edge/api/routes.py 路由调用其方法。
"""

from __future__ import annotations

import os
import threading
import time
import uuid
from collections import deque
from pathlib import Path

import cv2
import numpy as np

# 关闭 OpenCV 全局日志（避免 OBSensor/DSHOW 等驱动报错刷屏）
os.environ["OPENCV_LOG_LEVEL"] = "ERROR"
os.environ["OPENCV_VIDEOIO_PRIORITY_LIST"] = "FFMPEG"  # 跳过 OBSensor 后端
os.environ["LIBMODE_SENSOR_LOG_LEVEL"] = "error"

from .capture.camera import make_camera
from .classify.alert import AlertEngine
from .classify.decision import Action, classify
from .config import edge_settings
from .inference.detector import CLASS_COLORS, YOLODetector
from .inference.visual import put_chinese_text
from .network.http_client import build_payload, upload_sync
from .network.mqtt_client import EdgeMQTTClient
from .network.offline_cache import OfflineCache, get_cache
from .tracking import DefectTracker

_server: EdgeServer | None = None


def get_server() -> EdgeServer | None:
    return _server


class EdgeServer:
    """检测控制器 + MJPEG 帧管理。API 路由层调用此类方法。"""

    def __init__(self, host: str | None = None, port: int | None = None) -> None:
        global _server
        _server = self

        self._host = host if host is not None else edge_settings.server_host
        self._port = port if port is not None else edge_settings.server_port
        self._mqtt: EdgeMQTTClient | None = None

        # 离线缓存（断网容错）
        self._cache: OfflineCache = get_cache()
        self._cache_stop = threading.Event()

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
        """初始化 MQTT 连接。HTTP 服务由 server.py 的 main() 启动。"""
        self._mqtt = EdgeMQTTClient()
        if self._mqtt.connect():
            print(f"[EdgeServer] MQTT 已连接 {edge_settings.mqtt_broker_host}:{edge_settings.mqtt_broker_port}")
        else:
            print("[EdgeServer] MQTT 连接失败，将回退到 HTTP")
            self._mqtt = None

        self._cache.set_upload_func(self._retry_upload)
        self._cache_stop.clear()
        self._cache.start_retry_loop(self._cache_stop)

    def stop(self) -> None:
        self.stop_detection()
        self._stream_running = False
        if self._mqtt:
            self._mqtt.disconnect()
            self._mqtt = None
        self._cache_stop.set()
        print("[EdgeServer] 已停止")

    def _retry_upload(self, payload: dict, image: bytes) -> bool:
        """补传回调：离线缓存重试时调用。成功返回 True。"""
        try:
            data, files = build_payload(
                payload["device_id"], payload["detections"], payload["reason"],
                payload["avg_confidence"], payload["inference_ms"], payload["timestamp"],
                frame_jpg=image, decision=payload.get("decision", "CLOUD"),
            )
            import httpx
            resp = httpx.post(
                f"{self._api_url}/detect/upload",
                data=data, files=files,
                timeout=edge_settings.upload_http_timeout,
            )
            resp.raise_for_status()
            return True
        except Exception as e:
            return False

    # ── 配置 ──

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

    # ── 文件 / 摄像头 ──

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
        import io, os, sys
        available = []
        for idx in range(edge_settings.camera_probe_max):
            old_stderr = sys.stderr
            sys.stderr = io.StringIO()
            try:
                cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
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

    # ── 控制 ──

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
        pending = self._cache.pending_count()
        print(f"[EdgeServer] 检测启动 source={self._source}" +
              (f" (离线缓存{pending}条待补传)" if pending > 0 else ""))
        return {"ok": True, "status": "started", "source": self._source, "cache_pending": pending}

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
        s = dict(self._status)
        s["cache_pending"] = self._cache.pending_count()
        return s

    def get_summary(self) -> dict:
        return {
            "total": len(self._records),
            "cloud_count": self._cloud_count,
            "edge_count": self._edge_count,
            "cache_pending": self._cache.pending_count(),
            "records": self._records,
        }

    # ── 帧推送 ──

    def push_frame(self, frame: np.ndarray) -> None:
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
                                print(f"  [MQTT上传] [{dec_str}] {decision.summary}")
                            else:
                                print(f"  [MQTT上传失败] 缓存到本地队列")
                                self._cache.save({
                                    "device_id": self._device_id,
                                    "detections": new_defects,
                                    "reason": decision.reason,
                                    "avg_confidence": result.avg_confidence,
                                    "inference_ms": result.inference_ms,
                                    "timestamp": result.timestamp,
                                    "decision": dec_str,
                                }, jpg_bytes)
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
                                print(f"  [上传失败] {e} — 缓存到本地队列")
                                self._cache.save({
                                    "device_id": self._device_id,
                                    "detections": new_defects,
                                    "reason": decision.reason,
                                    "avg_confidence": result.avg_confidence,
                                    "inference_ms": result.inference_ms,
                                    "timestamp": result.timestamp,
                                    "decision": dec_str,
                                }, jpg_bytes)

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
                self.push_frame(annotated)

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