"""边缘端 FastAPI 应用工厂 + uvicorn 启动。

由 edge/main.py --server 模式调用，或直接 python -m edge.server 调试。

职责划分:
    server.py   — FastAPI 应用实例 + uvicorn 启动
    api/routes.py — HTTP 路由（薄层，调 service）
    service.py   — EdgeServer 业务逻辑（检测、MQTT、帧管理）
"""

from __future__ import annotations

import time
import threading

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from .api.routes import router
from .service import EdgeServer

app = FastAPI(title="Edge Server", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


def main() -> None:
    """命令行入口：python -m edge.server"""
    server = EdgeServer()
    server.configure(source="0")
    server.start()

    config = uvicorn.Config(app, host=server._host, port=server._port, log_level="warning")
    uvicorn_server = uvicorn.Server(config)
    threading.Thread(target=uvicorn_server.run, daemon=True).start()
    print(f"[EdgeServer] http://{server._host}:{server._port}  (stream /api/*)")
    print("[EdgeServer] 按 Ctrl+C 退出")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        server.stop()


if __name__ == "__main__":
    main()