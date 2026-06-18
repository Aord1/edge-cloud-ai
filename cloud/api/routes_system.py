"""系统状态接口 — 边缘端 + 云端运行指标，供前端状态监控页。"""

from __future__ import annotations

import platform
import time
from datetime import datetime, timedelta, timezone

import psutil
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..api.deps import get_db
from ..config import settings
from ..db.models import DetectionLog

router = APIRouter(prefix="/api/v1/system", tags=["system"])

TZ = timezone(timedelta(hours=settings.timezone_hours))
_start_time = time.time()


class SystemStatusResponse(BaseModel):
    cloud: dict
    edge: dict
    database: dict


@router.get("/status", response_model=SystemStatusResponse)
async def system_status(db: AsyncSession = Depends(get_db)) -> SystemStatusResponse:
    # 云端指标
    cpu = psutil.cpu_percent(interval=0.5)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")

    # 数据库指标
    total_r = await db.execute(select(func.count()).select_from(DetectionLog))
    db_total = total_r.scalar() or 0

    since = datetime.now(tz=TZ) - timedelta(hours=1)
    recent_r = await db.execute(
        select(func.count()).select_from(DetectionLog).where(DetectionLog.created_at >= since)
    )
    db_recent_1h = recent_r.scalar() or 0

    return SystemStatusResponse(
        cloud={
            "host": platform.node(),
            "platform": f"{platform.system()} {platform.release()}",
            "python": platform.python_version(),
            "uptime_sec": round(time.time() - _start_time, 0),
            "cpu_percent": cpu,
            "cpu_cores": psutil.cpu_count(),
            "mem_total_mb": round(mem.total / 1024 / 1024),
            "mem_used_mb": round(mem.used / 1024 / 1024),
            "mem_percent": mem.percent,
            "disk_total_gb": round(disk.total / 1024 / 1024 / 1024, 1),
            "disk_used_gb": round(disk.used / 1024 / 1024 / 1024, 1),
            "disk_percent": disk.percent,
        },
        edge={
            "note": "边缘端指标需轮询 /api/status（Edge Server 8080）",
        },
        database={
            "total_records": db_total,
            "recent_1h": db_recent_1h,
            "host": settings.db_host,
            "port": settings.db_port,
            "name": settings.db_name,
        },
    )
