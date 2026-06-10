"""云端主入口 — FastAPI 应用 + 生命周期管理。"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .db.engine import dispose_engine, get_engine
from .db.models import Base
from .api.routes_detect import router as detect_router
from .api.routes_chat import router as chat_router
from .api.routes_defects import router as defects_router
from .mqtt.handler import start_mqtt, stop_mqtt
from .services.review import process_upload, start_review_consumer

_bridge_task: asyncio.Task | None = None


async def _process_mqtt_bridge(queue: asyncio.Queue) -> None:
    while True:
        msg = await queue.get()
        try:
            await process_upload(**msg)
        except Exception as e:
            print(f"[MQTT Bridge] 处理失败: {e}")
        queue.task_done()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _bridge_task

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    await start_review_consumer()

    bridge_queue: asyncio.Queue = asyncio.Queue(maxsize=200)
    start_mqtt(bridge_queue)
    _bridge_task = asyncio.create_task(_process_mqtt_bridge(bridge_queue))

    yield

    stop_mqtt()
    if _bridge_task:
        _bridge_task.cancel()
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
