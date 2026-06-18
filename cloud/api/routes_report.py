"""质检报告接口 — 查询结构化的复核报告。"""

from __future__ import annotations

from datetime import timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..api.deps import get_db
from ..config import settings
from ..db.models import DetectionLog

router = APIRouter(prefix="/api/v1", tags=["report"])

TZ = timezone(timedelta(hours=settings.timezone_hours))

CLASS_CN = {
    "crazing": "裂纹", "inclusion": "夹杂", "patches": "斑块",
    "pitted_surface": "麻点", "rolled_in_scale": "氧化皮", "scratches": "划痕",
    "rolled-in_scale": "氧化皮",
}


class DefectItem(BaseModel):
    class_name: str
    confidence: float
    bbox: list[float]


class ReportResponse(BaseModel):
    defect_id: str
    device_id: str
    created_at: str
    inference_ms: float
    avg_confidence: float
    defect_types: list[str]
    defect_count: int
    reason: str
    decision: str
    defections: list[DefectItem]
    verdict: str
    reasoning: str
    recommendation: str
    reviewed_by: str
    reviewed_at: str


@router.get("/report/{defect_id}", response_model=ReportResponse)
async def get_report(
    defect_id: str,
    db: AsyncSession = Depends(get_db),
) -> ReportResponse:
    try:
        uid = UUID(defect_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的记录 ID")

    row = await db.get(DetectionLog, uid)
    if not row:
        raise HTTPException(status_code=404, detail="记录未找到")

    dets = row.detections if isinstance(row.detections, list) else []
    defect_types = list(set(
        CLASS_CN.get(d.get("class_name", ""), d.get("class_name", "?"))
        for d in dets
    ))

    review = row.agent_review
    if isinstance(review, dict):
        verdict = review.get("verdict", "")
        reasoning = review.get("reasoning", "")
        recommendation = review.get("recommendation", "")
        reviewed_at = review.get("reviewed_at", "")
        reviewed_by = review.get("reviewed_by", "")
    else:
        verdict = ""
        reasoning = "尚未复核"
        recommendation = ""
        reviewed_at = ""
        reviewed_by = ""

    return ReportResponse(
        defect_id=str(row.id),
        device_id=row.device_id,
        created_at=row.created_at.astimezone(TZ).isoformat() if row.created_at else "",
        inference_ms=row.inference_ms,
        avg_confidence=row.avg_confidence,
        defect_types=defect_types,
        defect_count=len(dets),
        reason=row.reason,
        decision=row.decision,
        defections=[DefectItem(
            class_name=d.get("class_name", "?"),
            confidence=d.get("confidence", 0),
            bbox=d.get("bbox", []),
        ) for d in dets],
        verdict=verdict,
        reasoning=reasoning,
        recommendation=recommendation,
        reviewed_by=reviewed_by or "",
        reviewed_at=reviewed_at,
    )
