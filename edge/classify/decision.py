"""检测结果分类 — 简单场景本地告警，复杂场景上传云端。"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from ..inference.detector import Detection, FrameResult

SIMPLE_CLASSES = {"person", "car", "truck", "bus", "bicycle", "motorcycle", "traffic light"}


class Action(Enum):
    EDGE = "edge"    # 本地处理
    CLOUD = "cloud"  # 上传云端


@dataclass
class Decision:
    action: Action
    reason: str
    local: list[Detection] = field(default_factory=list)
    upload: list[Detection] = field(default_factory=list)
    summary: str = ""


def classify(result: FrameResult, conf_edge: float = 0.5) -> Decision:
    dets = result.detections
    if not dets:
        return Decision(Action.EDGE, "empty", summary="无目标")

    # 高置信简单类 → 本地；其余 → 上传
    local = [d for d in dets if d.class_name in SIMPLE_CLASSES and d.confidence >= conf_edge]
    upload = [d for d in dets if d not in local]

    # 有复杂类或低置信度 → 上传
    if upload:
        reason = "complex_class" if any(d.class_name not in SIMPLE_CLASSES for d in upload) else "low_confidence"
        return Decision(Action.CLOUD, reason, local=local, upload=upload,
                        summary=f"上传 {len(upload)} 条 (复杂类/低置信度)")

    # 多目标 → 上传
    if len(local) > 10:
        return Decision(Action.CLOUD, "crowded", upload=dets,
                        summary=f"目标过多 ({len(dets)} > 10)")

    # 纯简单高置信 → 本地
    return Decision(Action.EDGE, "simple", local=local,
                    summary=f"本地处理 {len(local)} 个目标")
