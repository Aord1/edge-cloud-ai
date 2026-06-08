"""缺陷记录查询接口 — 供 Web 端轮询最近检测结果。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..api.deps import get_db
from ..db.models import DetectionLog
from ..schemas.detection import DetectionLogOut

router = APIRouter(prefix="/api/v1", tags=["defects"])


@router.get("/defects", response_model=list[DetectionLogOut])
async def list_defects(
    limit: int = Query(default=30, ge=1, le=100),
    device_id: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> list[DetectionLogOut]:
    stmt = select(DetectionLog).order_by(DetectionLog.created_at.desc()).limit(limit)
    if device_id:
        stmt = stmt.where(DetectionLog.device_id == device_id)
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return [DetectionLogOut.model_validate(r) for r in rows]
