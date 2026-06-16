"""Agent 工具基类 — 提供数据库会话与公共配置。"""

from __future__ import annotations

from abc import abstractmethod
from contextlib import asynccontextmanager
from datetime import timedelta, timezone
from typing import AsyncGenerator

from langchain_core.tools import BaseTool
from pydantic import BaseModel

from ...config import settings
from ...db.session import AsyncSessionLocal

TZ = timezone(timedelta(hours=settings.timezone_hours))


class AgentBaseTool(BaseTool):
    """所有 Agent 工具的基类，提供异步 DB 会话和时区。

    子类只需实现 `_run` / `_arun`，通过 self.get_db() 获取数据库会话，
    通过 self.TZ 访问项目时区。
    """

    TZ: timezone = TZ

    @asynccontextmanager
    async def get_db(self) -> AsyncGenerator:
        """异步数据库会话上下文管理器，工具内统一通过此方法获取 session。"""
        async with AsyncSessionLocal() as session:
            yield session