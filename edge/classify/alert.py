"""本地告警引擎 — 缺陷检测告警。"""

from __future__ import annotations

import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime

from ..inference.detector import SEVERE_DEFECTS, Detection


@dataclass
class Alert:
    alert_type: str
    message: str
    detections: list[Detection]
    timestamp: float = field(default_factory=time.time)

    @property
    def time_str(self) -> str:
        return datetime.fromtimestamp(self.timestamp).isoformat()


class AlertEngine:
    def __init__(self, cooldown_sec: float = 30.0) -> None:
        self.cooldown_sec = cooldown_sec
        self._last: dict[str, float] = {}
        self._history: list[Alert] = []

    def evaluate(self, detections: list[Detection]) -> Alert | None:
        if not detections:
            return None

        # 按缺陷严重程度归类
        severe = [d for d in detections if d.class_name in SEVERE_DEFECTS]
        names = {d.class_name for d in detections}

        if severe:
            atype = "severe"
            msg_detail = _fmt(_counts(severe))
        elif len(names) > 1:
            atype = "multiple"
            msg_detail = _fmt(_counts(detections))
        elif len(detections) > 3:
            atype = "dense"
            msg_detail = f"{len(detections)} 个"
        else:
            atype = "defect"
            msg_detail = _fmt(_counts(detections))

        # 冷却检查
        now = time.time()
        if now - self._last.get(atype, 0) < self.cooldown_sec:
            return None
        self._last[atype] = now

        alert = Alert(alert_type=atype,
                      message=f"[缺陷告警] {msg_detail}",
                      detections=detections)
        self._history.append(alert)
        if len(self._history) > 200:
            self._history = self._history[-200:]
        return alert

    def recent(self, n: int = 20) -> list[Alert]:
        return self._history[-n:]


def _counts(detections: list[Detection]) -> dict[str, int]:
    return dict(Counter(d.class_name for d in detections))


def _fmt(counts: dict[str, int]) -> str:
    return ", ".join(f"{k}×{v}" for k, v in counts.items())
