"""检测结果分类 — 高置信缺陷本地告警，复杂/低置信场景上传云端。"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from ..inference.detector import NEU_DET_CLASSES, SEVERE_DEFECTS, Detection, FrameResult


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
        return Decision(Action.EDGE, "empty", summary="无缺陷")

    # 有效缺陷
    valid = [d for d in dets if d.class_name in NEU_DET_CLASSES]
    if not valid:
        return Decision(Action.EDGE, "no_defect", summary="无有效缺陷")

    # 低置信 → 上传
    low_conf = [d for d in valid if d.confidence < conf_edge]
    # 严重缺陷 → 上传（即使置信度够高）
    severe = [d for d in valid if d.confidence >= conf_edge and d.class_name in SEVERE_DEFECTS]
    # 普通高置信 → 本地
    local = [d for d in valid if d.confidence >= conf_edge and d.class_name not in SEVERE_DEFECTS]

    upload = low_conf + severe

    # 多缺陷混杂 → 全部上传
    defect_types = {d.class_name for d in valid}
    if len(defect_types) > 2:
        return Decision(Action.CLOUD, "mixed_defects", upload=valid,
                        summary=f"混杂 {len(defect_types)} 类缺陷，上传深度分析")

    # 目标过多 → 上传
    if len(valid) > 5:
        return Decision(Action.CLOUD, "crowded", upload=valid,
                        summary=f"缺陷过多 ({len(valid)} > 5)")

    # 有需上传的
    if upload:
        reasons = []
        if low_conf:
            reasons.append(f"低置信 {len(low_conf)} 条")
        if severe:
            reasons.append(f"严重缺陷 {len(severe)} 条")
        return Decision(Action.CLOUD, "review", local=local, upload=upload,
                        summary="; ".join(reasons))

    # 纯普通高置信 → 本地
    return Decision(Action.EDGE, "simple", local=local,
                    summary=f"本地处理 {len(local)} 个缺陷")
