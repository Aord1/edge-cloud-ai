"""LLM 工厂 — 基于配置创建 ChatOpenAI 实例。"""

from __future__ import annotations

from langchain_openai import ChatOpenAI

from ...config import settings


def create_llm() -> ChatOpenAI:
    """根据云配置创建 ChatOpenAI 实例。"""
    kwargs: dict = {
        "model": settings.llm_model,
        "api_key": settings.llm_api_key,
        "temperature": 0.3,
        "streaming": True,
    }
    if settings.llm_base_url:
        kwargs["base_url"] = settings.llm_base_url
    return ChatOpenAI(**kwargs)
