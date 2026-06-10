"""检测相关 Pydantic Schema。"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import ConfigDict, BaseModel, Field


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


class DefectReviewOut(BaseModel):
    id: UUID
    defect_log_id: UUID
    verdict: str = ""
    reasoning_chain: dict | None = None
    tool_calls: dict | None = None
    reviewed_by: str = ""
    reviewed_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class DetectionLogOut(BaseModel):
    id: UUID
    device_id: str
    reason: str
    decision: str = "CLOUD"
    detections: list[DetectionItem]
    avg_confidence: float
    inference_ms: float
    image_path: str | None = None
    agent_review: dict | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
