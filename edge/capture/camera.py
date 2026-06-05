"""视频采集模块 — 多源支持、与推理解耦。"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass

import cv2
import numpy as np


@dataclass
class CaptureConfig:
    source: str | int = 0
    width: int = 640
    height: int = 480
    target_fps: int = 30
    buffer_size: int = 4


class Camera:
    """摄像头用后台线程，视频文件用同步读取。"""

    def __init__(self, cfg: CaptureConfig | None = None) -> None:
        cfg = cfg or CaptureConfig()
        self._source = int(cfg.source) if str(cfg.source).isdigit() else cfg.source
        self._width = cfg.width
        self._height = cfg.height
        self._target_fps = float(cfg.target_fps) if cfg.target_fps > 0 else 0.0
        self._cap: cv2.VideoCapture | None = None
        self._buffer: deque[np.ndarray] = deque(maxlen=cfg.buffer_size)
        self._running = False
        self._thread: threading.Thread | None = None
        self._is_live: bool = False
        self._fps: float = 30.0

    # ── 生命周期 ──────────────────────────────────────────────

    def open(self) -> None:
        self._cap = cv2.VideoCapture(self._source)
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self._width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._height)
        if not self._cap.isOpened():
            raise RuntimeError(f"无法打开视频源: {self._source}")
        self._is_live = isinstance(self._source, int)
        if self._target_fps <= 0:
            native = self._cap.get(cv2.CAP_PROP_FPS)
            self._target_fps = native if native > 0 else 30.0
        self._fps = self._target_fps
        if self._is_live:
            self._running = True
            self._thread = threading.Thread(target=self._capture_loop, daemon=True)
            self._thread.start()

    def close(self) -> None:
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=3)
        if self._cap is not None:
            self._cap.release()

    # ── 对外接口 ──────────────────────────────────────────────

    def read(self, timeout: float = 2.0) -> np.ndarray | None:
        """获取一帧。摄像头走缓冲，视频文件直接读。"""
        if self._is_live:
            return self._read_live(timeout)
        return self._read_file()

    @property
    def fps(self) -> float:
        return self._fps

    @property
    def is_live(self) -> bool:
        return self._is_live

    # ── 内部 ──────────────────────────────────────────────────

    def _read_live(self, timeout: float) -> np.ndarray | None:
        deadline = time.monotonic() + timeout
        while self._running or len(self._buffer) > 0:
            try:
                return self._buffer.pop()
            except IndexError:
                if time.monotonic() > deadline:
                    return None
                time.sleep(0.01)
        return None

    def _read_file(self) -> np.ndarray | None:
        ret, frame = self._cap.read()
        return frame if ret else None

    def _capture_loop(self) -> None:
        interval = 1.0 / self._target_fps
        last = 0.0
        while self._running:
            ret, frame = self._cap.read()
            if not ret:
                self._running = False
                break
            now = time.perf_counter()
            if now - last < interval:
                continue
            last = now
            self._buffer.append(frame)

    def __enter__(self) -> Camera:
        self.open()
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


def make_camera(source: str | int = 0, width: int = 640, height: int = 480,
                fps: int = 30) -> Camera:
    return Camera(CaptureConfig(source=source, width=width, height=height, target_fps=fps))
