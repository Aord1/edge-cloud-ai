"""LLM 工厂 — 基于运行时配置创建 ChatOpenAI 实例（支持热切换）。"""

from __future__ import annotations

from langchain_openai import ChatOpenAI

from ..llm_config import llm_runtime


def create_llm() -> ChatOpenAI:
    """根据运行时配置创建 ChatOpenAI 实例。

    API Key 未配置时使用占位符，调用 LLM 时会报明确错误。
    """
    kwargs: dict = {
        "model": llm_runtime.model,
        "api_key": llm_runtime.api_key or "sk-not-configured",
        "temperature": llm_runtime.temperature,
        "streaming": True,
    }
    if llm_runtime.base_url:
        kwargs["base_url"] = llm_runtime.base_url
    return ChatOpenAI(**kwargs)
