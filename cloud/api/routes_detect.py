"""检测数据上传接口。"""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession

from ..api.deps import get_db
from ..db.models import DetectionLog
from ..schemas.detection import DetectionUploadResponse

router = APIRouter(prefix="/api/v1", tags=["detection"])

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)


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
    import json

    dets = json.loads(detections)

    # 保存关键帧（如果有）
    image_path = None
    if image and image.filename:
        fname = f"{uuid.uuid4().hex}_{image.filename}"
        filepath = UPLOAD_DIR / fname
        filepath.write_bytes(await image.read())
        image_path = str(filepath)

    # 写入数据库
    log = DetectionLog(
        device_id=device_id,
        reason=reason,
        detections=dets,
        image_path=image_path,
        avg_confidence=avg_confidence,
        inference_ms=inference_ms,
    )
    db.add(log)
    await db.flush()

    return DetectionUploadResponse(
        id=log.id,
        message=f"已接收 {len(dets)} 条检测结果",
    )
