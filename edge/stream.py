"""边缘端 MJPEG 流服务器 — Web 端实时查看检测画面。

用法:
    stream = EdgeStreamServer(host="0.0.0.0", port=8080)
    stream.start()
    stream.push_frame(annotated_frame)
    ...
    stream.stop()
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import cv2
import numpy as np

from .config import edge_settings


class _StreamHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/stream":
            self._serve_mjpeg()
        elif self.path == "/status":
            self._serve_status()
        else:
            self.send_error(404)

    def _serve_mjpeg(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Connection", "close")
        self.end_headers()
        server: EdgeStreamServer = self.server._owner  # type: ignore[attr-defined]
        while server._running:
            frame = server._pop_frame(timeout=edge_settings.mjpeg_frame_timeout)
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

    def _serve_status(self) -> None:
        server: EdgeStreamServer = self.server._owner  # type: ignore[attr-defined]
        data = json.dumps(server._status).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format, *args) -> None:
        pass  # 静默日志


class EdgeStreamServer:
    """轻量 MJPEG 流服务器，后台线程运行。"""

    def __init__(self, host: str | None = None, port: int | None = None) -> None:
        self._host = host if host is not None else edge_settings.server_host
        self._port = port if port is not None else edge_settings.server_port
        self._server: HTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._running = False
        self._frame: np.ndarray | None = None
        self._lock = threading.Lock()
        self._cond = threading.Condition(self._lock)
        self._status: dict = {"detections": [], "count": 0, "fps": 0.0}

    def start(self) -> None:
        self._running = True
        self._server = HTTPServer((self._host, self._port), _StreamHandler)
        self._server._owner = self  # type: ignore[attr-defined]
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        print(f"[Stream] MJPEG 流服务启动 http://{self._host}:{self._port}/stream")

    def stop(self) -> None:
        self._running = False
        if self._server:
            self._server.shutdown()
        if self._thread:
            self._thread.join(timeout=edge_settings.server_thread_join_timeout)
        print("[Stream] 流服务已停止")

    def push_frame(self, frame: np.ndarray) -> None:
        with self._lock:
            self._frame = frame.copy()
            self._cond.notify_all()

    def update_status(self, status: dict) -> None:
        self._status.update(status)

    def _pop_frame(self, timeout: float = 1.0) -> np.ndarray | None:
        with self._lock:
            if self._frame is None:
                self._cond.wait(timeout)
            frame, self._frame = self._frame, None
            return frame
