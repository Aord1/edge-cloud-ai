"""数据库引擎 — asyncpg 连接池。"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from ..config import settings

_engine: AsyncEngine | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            settings.db_url,
            pool_size=5,
            max_overflow=15,
            pool_recycle=3600,
            pool_pre_ping=True,
            pool_timeout=30,
            echo=False,
        )
    return _engine


async def dispose_engine() -> None:
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None
