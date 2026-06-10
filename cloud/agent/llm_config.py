"""LLM 运行时配置管理 — 支持热切换模型，无需重启服务。"""

from __future__ import annotations

from ..config import settings


class LLMRuntimeConfig:
    """线程安全的运行时 LLM 配置，支持热更新。"""

    def __init__(self) -> None:
        self.model: str = settings.llm_model
        self.base_url: str = settings.llm_base_url
        self.api_key: str = settings.llm_api_key
        self.temperature: float = settings.llm_temperature

    def update(
        self,
        model: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        temperature: float | None = None,
    ) -> None:
        if model is not None:
            self.model = model
        if base_url is not None:
            self.base_url = base_url
        if api_key is not None:
            self.api_key = api_key
        if temperature is not None:
            self.temperature = temperature

    def as_dict(self) -> dict:
        return {
            "model": self.model,
            "base_url": self.base_url,
            "temperature": self.temperature,
            "api_key": self.api_key[:8] + "..." if self.api_key else "",
        }


llm_runtime = LLMRuntimeConfig()
