"""检测相关 Pydantic Schema。"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class DetectionItem(BaseModel):
    class_name: str
    class_id: int
    confidence: float
    bbox: list[int]  # [x1, y1, x2, y2]


class DetectionUploadRequest(BaseModel):
    device_id: str = Field(..., max_length=64)
    reason: str = Field(..., max_length=64)
    detections: list[DetectionItem]
    avg_confidence: float
    inference_ms: float
    timestamp: float


class DetectionUploadResponse(BaseModel):
    id: UUID
    status: str = "received"
    message: str = "检测数据已接收"


class DetectionLogOut(BaseModel):
    id: UUID
    device_id: str
    reason: str
    detections: list[DetectionItem]
    avg_confidence: float
    inference_ms: float
    created_at: datetime

    model_config = dict(from_attributes=True)
