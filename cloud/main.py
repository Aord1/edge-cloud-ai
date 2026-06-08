"""云端主入口 — FastAPI 应用 + 生命周期管理。"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .db.engine import dispose_engine, get_engine
from .db.models import Base
from .api.routes_detect import router as detect_router
from .api.routes_chat import router as chat_router
from .api.routes_defects import router as defects_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup — 建表
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    # shutdown — 释放连接池
    await dispose_engine()


app = FastAPI(
    title="EdgeCloud AI",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(detect_router)
app.include_router(chat_router)
app.include_router(defects_router)


def main() -> None:
    import uvicorn
    uvicorn.run(
        "cloud.main:app",
        host=settings.cloud_host,
        port=settings.cloud_port,
        reload=settings.environment == "development",
    )


if __name__ == "__main__":
    main()
