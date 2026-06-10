"""检测数据上传接口 — HTTP multipart 上传。"""

from __future__ import annotations

import base64
import json
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession

from ..api.deps import get_db
from ..schemas.detection import DetectionUploadResponse
from ..services.review import process_upload, start_review_consumer

router = APIRouter(prefix="/api/v1", tags=["detection"])


@router.post("/detect/upload", response_model=DetectionUploadResponse)
async def upload_detection(
    device_id: str = Form(...),
    reason: str = Form(...),
    detections: str = Form(...),
    avg_confidence: float = Form(...),
    inference_ms: float = Form(...),
    timestamp: float = Form(...),
    image: UploadFile = File(None),
    db: AsyncSession = Depends(get_db),
) -> DetectionUploadResponse:
    dets = json.loads(detections)

    image_b64 = ""
    if image and image.filename:
        image_b64 = base64.b64encode(await image.read()).decode()

    log = await process_upload(
        device_id=device_id,
        reason=reason,
        detections=dets,
        avg_confidence=avg_confidence,
        inference_ms=inference_ms,
        image_b64=image_b64,
    )

    return DetectionUploadResponse(
        id=log.id,
        message=f"已接收 {len(dets)} 条检测结果",
    )
