"""缺陷帧间跟踪 — 基于 IoU 匹配，同一缺陷只上报一次。"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid4

from .config import edge_settings


def _iou(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    """计算两个边界框的 IoU。"""
    x1 = max(a[0], b[0])
    y1 = max(a[1], b[1])
    x2 = min(a[2], b[2])
    y2 = min(a[3], b[3])
    if x1 >= x2 or y1 >= y2:
        return 0.0
    inter = (x2 - x1) * (y2 - y1)
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    return inter / (area_a + area_b - inter + 1e-6)


@dataclass
class TrackedDefect:
    track_id: str
    class_name: str
    bbox: tuple[int, int, int, int]
    uploaded: bool = False
    frames_seen: int = 1


class DefectTracker:
    """轻量 IoU 跟踪器 — 为每个缺陷分配稳定 ID，防止重复上报。"""

    def __init__(self, iou_threshold: float | None = None, min_frames: int | None = None) -> None:
        self._iou_threshold = iou_threshold if iou_threshold is not None else edge_settings.tracker_iou_threshold
        self._min_frames = min_frames if min_frames is not None else edge_settings.tracker_min_frames
        self._tracks: list[TrackedDefect] = []
        self._uploaded_ids: set[str] = set()

    def update(self, detections: list) -> list[dict]:
        """
        传入当前帧检测结果列表，返回需要上报的缺陷列表（含 track_id）。

        每个 detection 格式: Detection 对象，有 class_name, confidence, bbox 属性。
        """
        matched_track_ids: set[str] = set()
        updates: list[dict] = []

        for det in detections:
            best_iou = 0.0
            best_track = None
            for t in self._tracks:
                if t.class_name != det.class_name:
                    continue
                i = _iou(det.bbox, t.bbox)
                if i > best_iou:
                    best_iou = i
                    best_track = t

            if best_iou >= self._iou_threshold and best_track is not None:
                # 匹配到已有跟踪
                best_track.bbox = det.bbox
                best_track.frames_seen += 1
                matched_track_ids.add(best_track.track_id)
                if (not best_track.uploaded
                        and best_track.frames_seen >= self._min_frames
                        and best_track.track_id not in self._uploaded_ids):
                    best_track.uploaded = True
                    self._uploaded_ids.add(best_track.track_id)
                    updates.append({
                        "track_id": best_track.track_id,
                        "class_name": det.class_name,
                        "class_id": det.class_id,
                        "confidence": det.confidence,
                        "bbox": list(det.bbox),
                        "reason": "new_defect",
                    })
            else:
                # 新缺陷
                tid = uuid4().hex[:12]
                t = TrackedDefect(track_id=tid, class_name=det.class_name, bbox=det.bbox)
                self._tracks.append(t)
                matched_track_ids.add(tid)
                # 第 1 帧立即上报（避免延迟）
                if self._min_frames <= 1:
                    t.uploaded = True
                    self._uploaded_ids.add(tid)
                    updates.append({
                        "track_id": tid,
                        "class_name": det.class_name,
                        "class_id": det.class_id,
                        "confidence": det.confidence,
                        "bbox": list(det.bbox),
                        "reason": "new_defect",
                    })

        # 清除失配的跟踪
        self._tracks = [t for t in self._tracks if t.track_id in matched_track_ids]

        return updates

    def reset(self) -> None:
        """每次检测启动时调用，清空状态。"""
        self._tracks.clear()
        self._uploaded_ids.clear()
