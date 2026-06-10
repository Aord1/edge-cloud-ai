"""缺陷记录查询接口 — 分页查询，供 Web 端查看所有检测记录与 Agent 复核结果。"""

from __future__ import annotations

import shutil

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from ..api.deps import get_db
from ..config import settings
from ..db.models import DetectionLog
from ..schemas.detection import DetectionLogOut, DetectionLogPage

router = APIRouter(prefix="/api/v1", tags=["defects"])

UPLOAD_DIR = __import__("pathlib").Path("uploads")


@router.get("/defects", response_model=DetectionLogPage)
async def list_defects(
    limit: int = Query(default=settings.api_defects_limit, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    device_id: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> DetectionLogPage:
    base = select(DetectionLog)
    count_stmt = select(func.count()).select_from(DetectionLog)

    if device_id:
        base = base.where(DetectionLog.device_id == device_id)
        count_stmt = count_stmt.where(DetectionLog.device_id == device_id)

    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0

    stmt = base.order_by(DetectionLog.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(stmt)
    rows = result.scalars().all()

    return DetectionLogPage(
        total=total,
        items=[DetectionLogOut.model_validate(r) for r in rows],
    )


@router.delete("/defects")
async def delete_all_defects(
    db: AsyncSession = Depends(get_db),
) -> dict:
    await db.execute(delete(DetectionLog))
    await db.commit()

    if UPLOAD_DIR.exists():
        shutil.rmtree(UPLOAD_DIR)
        UPLOAD_DIR.mkdir()

    return {"ok": True, "message": "所有检测记录已清除"}


@router.get("/defects/{defect_id}/image")
async def get_defect_image(
    defect_id: str,
    db: AsyncSession = Depends(get_db),
):
    from uuid import UUID
    try:
        uid = UUID(defect_id)
    except ValueError:
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": "invalid id"}, status_code=400)

    result = await db.execute(
        select(DetectionLog.image_path).where(DetectionLog.id == uid)
    )
    image_path = result.scalar_one_or_none()

    if image_path:
        path = Path(image_path)
        if path.exists():
            return FileResponse(path, media_type="image/jpeg")

    from fastapi.responses import JSONResponse
    return JSONResponse({"error": "image not found"}, status_code=404)
