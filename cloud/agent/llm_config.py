"""LLM 运行时配置管理 — 基于数据库的多 Profile 热切换。

设计模式参照 cc-switch：
- 每套配置（模型+地址+密钥+温度）存为一条 profile 记录
- 仅一条记录 is_active=true，切换即改激活标记
- API Key 随 profile 存储，.env 中的 LLM_API_KEY 作为全局回退
- 首次启动时自动迁移旧的 llm_config.json 到数据库
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import select, update

_LEGACY_CONFIG_FILE = Path(__file__).resolve().parent.parent.parent / "llm_config.json"


@dataclass
class ProfileData:
    id: str = ""
    name: str = ""
    model: str = ""
    base_url: str = ""
    api_key_set: bool = False
    temperature: float = 0.3
    is_active: bool = False


class LLMRuntimeConfig:
    """运行时 LLM 配置，基于 PostgreSQL llm_profiles 表。

    切换模型 = 更新 is_active 标记 + Agent reconfigure()。
    """

    def __init__(self) -> None:
        self.model: str = ""
        self.base_url: str = ""
        self.api_key: str = ""
        self.temperature: float = 0.3
        self._active_profile_id: str = ""
        self._loaded = False

    # ── 公开 API ──

    async def load(self) -> None:
        """从数据库加载当前激活的 profile。若表为空则尝试迁移旧配置。"""
        from ..db.models import LlmProfile
        from ..db.session import AsyncSessionLocal

        if self._loaded:
            return

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(LlmProfile).where(LlmProfile.is_active == True).limit(1)
            )
            active = result.scalar_one_or_none()

            if active is None:
                existing = await session.execute(select(LlmProfile).limit(1))
                if existing.scalar_one_or_none() is None:
                    await self._migrate_legacy(session)

                result = await session.execute(
                    select(LlmProfile).where(LlmProfile.is_active == True).limit(1)
                )
                active = result.scalar_one_or_none()

            if active:
                self._apply(active)
            else:
                self.model = self.model or "gpt-4o"

        self._loaded = True

    async def list_profiles(self) -> list[ProfileData]:
        """返回所有 profile 列表（不含 api_key 明文）。"""
        from ..db.models import LlmProfile
        from ..db.session import AsyncSessionLocal

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(LlmProfile).order_by(LlmProfile.created_at.desc())
            )
            rows = result.scalars().all()
            return [
                ProfileData(
                    id=str(r.id),
                    name=r.name,
                    model=r.model,
                    base_url=r.base_url,
                    api_key_set=bool(r.api_key),
                    temperature=r.temperature,
                    is_active=r.is_active,
                )
                for r in rows
            ]

    async def create_profile(
        self,
        name: str,
        model: str,
        base_url: str = "",
        api_key: str = "",
        temperature: float = 0.3,
    ) -> ProfileData:
        """新建 profile 并返回。"""
        from ..db.models import LlmProfile
        from ..db.session import AsyncSessionLocal

        async with AsyncSessionLocal() as session:
            profile = LlmProfile(
                name=name,
                model=model,
                base_url=base_url,
                api_key=api_key,
                temperature=temperature,
                is_active=False,
            )
            session.add(profile)
            await session.commit()
            await session.refresh(profile)
            return ProfileData(
                id=str(profile.id),
                name=profile.name,
                model=profile.model,
                base_url=profile.base_url,
                api_key_set=bool(profile.api_key),
                temperature=profile.temperature,
                is_active=profile.is_active,
            )

    async def activate(self, profile_id: str) -> ProfileData:
        """切换激活指定 profile，并更新内存配置。"""
        from ..db.models import LlmProfile
        from ..db.session import AsyncSessionLocal

        async with AsyncSessionLocal() as session:
            await session.execute(
                update(LlmProfile).values(is_active=False)
            )
            result = await session.execute(
                select(LlmProfile).where(LlmProfile.id == profile_id)
            )
            profile = result.scalar_one_or_none()
            if profile is None:
                raise ValueError(f"Profile {profile_id} not found")
            profile.is_active = True
            await session.commit()
            await session.refresh(profile)
            self._apply(profile)
            return ProfileData(
                id=str(profile.id),
                name=profile.name,
                model=profile.model,
                base_url=profile.base_url,
                api_key_set=bool(profile.api_key),
                temperature=profile.temperature,
                is_active=True,
            )

    async def delete_profile(self, profile_id: str) -> None:
        """删除指定 profile（不允许删除当前激活的）。"""
        from ..db.models import LlmProfile
        from ..db.session import AsyncSessionLocal

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(LlmProfile).where(LlmProfile.id == profile_id)
            )
            profile = result.scalar_one_or_none()
            if profile is None:
                return
            if profile.is_active:
                raise ValueError("Cannot delete the active profile")
            await session.delete(profile)
            await session.commit()

    async def update_profile(
        self,
        profile_id: str,
        name: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        temperature: float | None = None,
    ) -> ProfileData:
        """更新指定 profile 的字段。"""
        from ..db.models import LlmProfile
        from ..db.session import AsyncSessionLocal

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(LlmProfile).where(LlmProfile.id == profile_id)
            )
            profile = result.scalar_one_or_none()
            if profile is None:
                raise ValueError(f"Profile {profile_id} not found")
            if name is not None:
                profile.name = name
            if model is not None:
                profile.model = model
            if base_url is not None:
                profile.base_url = base_url
            if api_key is not None:
                profile.api_key = api_key
            if temperature is not None:
                profile.temperature = temperature
            await session.commit()
            await session.refresh(profile)
            if profile.is_active:
                self._apply(profile)
            return ProfileData(
                id=str(profile.id),
                name=profile.name,
                model=profile.model,
                base_url=profile.base_url,
                api_key_set=bool(profile.api_key),
                temperature=profile.temperature,
                is_active=profile.is_active,
            )

    # ── 兼容旧接口 ──

    def as_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "base_url": self.base_url,
            "temperature": self.temperature,
            "api_key_set": bool(self.api_key),
            "active_profile_id": self._active_profile_id,
        }

    # ── 内部方法 ──

    def _apply(self, profile) -> None:
        from ..config import settings

        self.model = profile.model
        self.base_url = profile.base_url
        self.api_key = profile.api_key or getattr(settings, "llm_api_key", "")
        self.temperature = profile.temperature
        self._active_profile_id = str(profile.id)

    async def _migrate_legacy(self, session) -> None:
        """将旧 llm_config.json 迁移为首个激活 profile。"""
        from ..db.models import LlmProfile

        if not _LEGACY_CONFIG_FILE.exists():
            # 创建默认 profile
            default = LlmProfile(
                name="默认配置",
                model="gpt-4o",
                base_url="https://api.openai.com/v1",
                api_key="",
                temperature=0.3,
                is_active=True,
            )
            session.add(default)
            await session.commit()
            return

        try:
            data = json.loads(_LEGACY_CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            data = {}

        profile = LlmProfile(
            name="导入配置",
            model=data.get("model", "gpt-4o"),
            base_url=data.get("base_url", ""),
            api_key=data.get("api_key", ""),
            temperature=data.get("temperature", 0.3),
            is_active=True,
        )
        session.add(profile)
        await session.commit()

        # 迁移成功后删除旧文件
        try:
            _LEGACY_CONFIG_FILE.unlink(missing_ok=True)
        except Exception:
            pass


# 全局单例
llm_runtime = LLMRuntimeConfig()
