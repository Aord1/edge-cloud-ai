"""缺陷统计接口 — 按类型/时间/置信度聚合，供前端 ECharts 可视化。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from ..api.deps import get_db
from ..config import settings
from ..db.models import DetectionLog

router = APIRouter(prefix="/api/v1", tags=["stats"])

TZ = timezone(timedelta(hours=settings.timezone_hours))


class TypeCount(BaseModel):
    class_name: str
    count: int


class TrendPoint(BaseModel):
    time: str
    total: int
    cloud: int
    edge: int


class StatsResponse(BaseModel):
    total: int
    cloud_count: int
    edge_count: int
    reviewed_count: int
    pending_count: int
    type_distribution: list[TypeCount]
    confidence_buckets: list[int]
    trend: list[TrendPoint]


@router.get("/stats", response_model=StatsResponse)
async def get_stats(
    hours: int = Query(default=24, ge=1, le=720),
    db: AsyncSession = Depends(get_db),
) -> StatsResponse:
    since = datetime.now(tz=TZ) - timedelta(hours=hours)

    base = select(DetectionLog).where(DetectionLog.created_at >= since)

    # 总数 + 分流计数
    total_r = await db.execute(
        select(func.count()).select_from(DetectionLog).where(DetectionLog.created_at >= since)
    )
    total = total_r.scalar() or 0

    cloud_r = await db.execute(
        select(func.count()).select_from(DetectionLog).where(
            DetectionLog.created_at >= since, DetectionLog.decision == "CLOUD"
        )
    )
    cloud_count = cloud_r.scalar() or 0

    edge_count = total - cloud_count

    reviewed_r = await db.execute(
        select(func.count()).select_from(DetectionLog).where(
            DetectionLog.created_at >= since,
            DetectionLog.decision == "CLOUD",
            DetectionLog.agent_review.isnot(None),
        )
    )
    reviewed_count = reviewed_r.scalar() or 0
    pending_count = cloud_count - reviewed_count

    # 缺陷类型分布 — 从 JSONB detections 展开统计
    rows = await db.execute(base.order_by(DetectionLog.created_at.desc()))
    all_logs = rows.scalars().all()

    type_map: dict[str, int] = {}
    conf_buckets = [0] * 5  # [0-0.2, 0.2-0.4, 0.4-0.6, 0.6-0.8, 0.8-1.0]
    for log in all_logs:
        dets = log.detections if isinstance(log.detections, list) else []
        for d in dets:
            if isinstance(d, dict):
                cn = d.get("class_name", "unknown")
                type_map[cn] = type_map.get(cn, 0) + 1
        conf = log.avg_confidence or 0
        idx = min(int(conf * 5), 4)
        conf_buckets[idx] += 1

    type_distribution = [
        TypeCount(class_name=k, count=v) for k, v in sorted(type_map.items(), key=lambda x: -x[1])
    ]

    # 趋势 — 按小时分桶
    trend: list[TrendPoint] = []
    if total > 0:
        buckets: dict[str, dict] = {}
        for log in all_logs:
            t = log.created_at.astimezone(TZ)
            key = t.strftime("%m-%d %H:00")
            if key not in buckets:
                buckets[key] = {"total": 0, "cloud": 0, "edge": 0}
            buckets[key]["total"] += 1
            if log.decision == "CLOUD":
                buckets[key]["cloud"] += 1
            else:
                buckets[key]["edge"] += 1
        for key in sorted(buckets.keys()):
            v = buckets[key]
            trend.append(TrendPoint(time=key, **v))

    return StatsResponse(
        total=total,
        cloud_count=cloud_count,
        edge_count=edge_count,
        reviewed_count=reviewed_count,
        pending_count=pending_count,
        type_distribution=type_distribution,
        confidence_buckets=conf_buckets,
        trend=trend,
    )
