"""LLM 配置 API — 运行时获取和切换 LLM 模型。"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ..agent.llm_config import llm_runtime
from ..agent.orchestrator import agent

router = APIRouter(prefix="/api/v1", tags=["llm"])


class LLMConfigResponse(BaseModel):
    model: str
    base_url: str
    temperature: float
    api_key: str


class LLMConfigUpdate(BaseModel):
    model: str | None = Field(None, description="模型名称，如 gpt-4o / deepseek-chat")
    base_url: str | None = Field(None, description="API 地址")
    api_key: str | None = Field(None, description="API Key")
    temperature: float | None = Field(None, ge=0, le=2, description="温度 0-2")


@router.get("/llm/config", response_model=LLMConfigResponse)
async def get_llm_config() -> LLMConfigResponse:
    """获取当前 LLM 运行时配置。"""
    cfg = llm_runtime.as_dict()
    return LLMConfigResponse(**cfg)


@router.put("/llm/config", response_model=LLMConfigResponse)
async def update_llm_config(body: LLMConfigUpdate) -> LLMConfigResponse:
    """更新 LLM 配置并热切换 Agent 模型。"""
    llm_runtime.update(
        model=body.model,
        base_url=body.base_url,
        api_key=body.api_key,
        temperature=body.temperature,
    )
    agent.reconfigure()
    cfg = llm_runtime.as_dict()
    return LLMConfigResponse(**cfg)
