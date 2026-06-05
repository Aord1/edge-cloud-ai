"""本地告警引擎。"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime

from ..inference.detector import Detection


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

        # 归并告警类型
        classes = {d.class_name for d in detections}
        n = len(detections)
        if "person" in classes:
            atype = "crowd" if n >= 5 else "person"
        elif classes & {"car", "truck", "bus", "motorcycle"}:
            atype = "vehicle"
        else:
            atype = "object"

        # 冷却检查
        now = time.time()
        if now - self._last.get(atype, 0) < self.cooldown_sec:
            return None
        self._last[atype] = now

        names = ", ".join(f"{d.class_name}×{c}" for d, c in self._counts(detections).items())
        alert = Alert(alert_type=atype, message=f"[{atype}] {names}", detections=detections)
        self._history.append(alert)
        if len(self._history) > 200:
            self._history = self._history[-200:]
        return alert

    def recent(self, n: int = 20) -> list[Alert]:
        return self._history[-n:]

    @staticmethod
    def _counts(detections: list[Detection]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for d in detections:
            counts[d.class_name] = counts.get(d.class_name, 0) + 1
        return counts
