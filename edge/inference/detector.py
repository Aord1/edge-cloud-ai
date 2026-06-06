"""YOLO 检测引擎 — OpenVINO 推理。"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
import openvino as ov

MODEL_DIR = Path(__file__).resolve().parent.parent / "public" / "neu-det"

NEU_DET_CLASSES = [
    "crazing",          # 裂纹
    "inclusion",        # 夹杂
    "patches",          # 斑块
    "pitted_surface",   # 麻点
    "rolled-in_scale",  # 氧化皮
    "scratches",        # 划痕
]

SEVERE_DEFECTS = {"crazing", "rolled-in_scale", "inclusion"}

CLASS_COLORS: dict[int, tuple[int, int, int]] = {
    0: (0, 0, 255),       # crazing — 红
    1: (255, 128, 0),     # inclusion — 橙
    2: (0, 255, 255),     # patches — 黄
    3: (255, 0, 255),     # pitted_surface — 紫
    4: (128, 128, 128),   # rolled-in_scale — 灰
    5: (0, 255, 0),       # scratches — 绿
}


@dataclass
class Detection:
    class_name: str
    class_id: int
    confidence: float
    bbox: tuple[int, int, int, int]

    @property
    def x1(self) -> int: return self.bbox[0]

    @property
    def y1(self) -> int: return self.bbox[1]

    @property
    def x2(self) -> int: return self.bbox[2]

    @property
    def y2(self) -> int: return self.bbox[3]


@dataclass
class FrameResult:
    frame_id: int
    timestamp: float
    detections: list[Detection] = field(default_factory=list)
    inference_ms: float = 0.0

    @property
    def count(self) -> int:
        return len(self.detections)

    @property
    def avg_confidence(self) -> float:
        if not self.detections:
            return 1.0
        return sum(d.confidence for d in self.detections) / len(self.detections)

    @property
    def class_names(self) -> set[str]:
        return {d.class_name for d in self.detections}


class YOLODetector:
    def __init__(self, model_path: str | None = None,
                 conf_threshold: float = 0.25, max_detections: int = 20) -> None:
        model_path = model_path or str(MODEL_DIR / "yolo26n_neu_det.xml")
        self.conf_threshold = conf_threshold
        self.max_detections = max_detections

        core = ov.Core()
        model = core.read_model(model_path)
        self._compiled = core.compile_model(model, "CPU")
        self._infer = self._compiled.create_infer_request()

        input_tensor = model.inputs[0]
        self._input_key = input_tensor.any_name
        _, _, self._input_h, self._input_w = input_tensor.shape

        self._frame_counter = 0

    def detect(self, frame: np.ndarray) -> FrameResult:
        t0 = time.perf_counter()

        img, scale, pad = self._preprocess(frame)

        self._infer.set_tensor(self._input_key, ov.Tensor(img))
        self._infer.infer()

        raw = self._infer.get_output_tensor().data
        detections = self._postprocess(raw[0], scale, pad)

        elapsed = (time.perf_counter() - t0) * 1000
        self._frame_counter += 1

        return FrameResult(
            frame_id=self._frame_counter,
            timestamp=time.time(),
            detections=detections,
            inference_ms=round(elapsed, 2),
        )

    def annotate(self, frame: np.ndarray, result: FrameResult) -> np.ndarray:
        annotated = frame.copy()
        for d in result.detections:
            x1, y1, x2, y2 = d.bbox
            color = CLASS_COLORS.get(d.class_id, (0, 255, 0))
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
            label = f"{d.class_name} {d.confidence:.2f}"
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)
            cv2.rectangle(annotated, (x1, y1 - th - 4), (x1 + tw + 4, y1), color, -1)
            cv2.putText(annotated, label, (x1 + 2, y1 - 4),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
        fps = 1000 / result.inference_ms if result.inference_ms > 0 else 0
        cv2.putText(annotated, f"FPS: {fps:.1f}  Detections: {result.count}",
                    (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
        return annotated

    # ── 内部 ──────────────────────────────────────────────────

    def _preprocess(self, frame: np.ndarray) -> tuple[np.ndarray, float, tuple[int, int]]:
        h, w = frame.shape[:2]
        scale = min(self._input_w / w, self._input_h / h)
        new_w, new_h = int(w * scale), int(h * scale)
        resized = cv2.resize(frame, (new_w, new_h))
        pad_w = (self._input_w - new_w) // 2
        pad_h = (self._input_h - new_h) // 2
        padded = cv2.copyMakeBorder(resized, pad_h, self._input_h - new_h - pad_h,
                                    pad_w, self._input_w - new_w - pad_w,
                                    cv2.BORDER_CONSTANT, value=(114, 114, 114))
        # HWC → CHW, BGR → RGB, /255
        blob = padded[:, :, ::-1].transpose(2, 0, 1).astype(np.float32) / 255.0
        blob = np.expand_dims(blob, 0)
        return blob, scale, (pad_w, pad_h)

    def _postprocess(self, raw: np.ndarray, scale: float,
                     pad: tuple[int, int]) -> list[Detection]:
        # 模型已内置 sigmoid + NMS，输出 [300, 6]: [x1, y1, x2, y2, score, label]
        # score 已经是 [0,1] 置信度，直接过滤
        mask = raw[:, 4] > self.conf_threshold
        rows = raw[mask]
        if len(rows) == 0:
            return []

        rows = rows[np.argsort(rows[:, 4])[::-1]]
        rows = rows[:self.max_detections]

        pad_w, pad_h = pad
        results: list[Detection] = []
        for row in rows:
            x1, y1, x2, y2, score, label = row
            x1 = int((x1 - pad_w) / scale)
            y1 = int((y1 - pad_h) / scale)
            x2 = int((x2 - pad_w) / scale)
            y2 = int((y2 - pad_h) / scale)
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = max(0, x2), max(0, y2)
            if x2 <= x1 or y2 <= y1:
                continue

            cls_id = int(label)
            results.append(Detection(
                class_name=NEU_DET_CLASSES[cls_id] if cls_id < len(NEU_DET_CLASSES) else str(cls_id),
                class_id=cls_id,
                confidence=round(float(score), 4),
                bbox=(x1, y1, x2, y2),
            ))
        return results
