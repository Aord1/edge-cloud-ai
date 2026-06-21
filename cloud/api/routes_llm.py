"""LLM 配置 API — 多 Profile 管理 + 热切换。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..agent.llm_config import ProfileData, llm_runtime
from ..agent.orchestrator import agent
from ..services.review import start_review_consumer

router = APIRouter(prefix="/api/v1", tags=["llm"])


# ── 请求/响应模型 ──

class LlmConfigResponse(BaseModel):
    model: str
    base_url: str
    temperature: float
    api_key_set: bool
    active_profile_id: str


class ProfileResponse(BaseModel):
    id: str
    name: str
    model: str
    base_url: str
    api_key_set: bool
    temperature: float
    is_active: bool


class ProfileCreate(BaseModel):
    name: str = Field(..., min_length=1, description="配置名称，如 GPT分析 / DS快检")
    model: str = Field(..., min_length=1, description="模型名")
    base_url: str = Field(default="", description="API 地址")
    api_key: str = Field(default="", description="API Key")
    temperature: float = Field(default=0.3, ge=0, le=2)


class ProfileUpdate(BaseModel):
    name: str | None = Field(None)
    model: str | None = Field(None)
    base_url: str | None = Field(None)
    api_key: str | None = Field(None)
    temperature: float | None = Field(None, ge=0, le=2)


# ── 兼容旧接口（单模型模式 → 自动更新/创建当前激活 profile）──

@router.get("/llm/config", response_model=LlmConfigResponse)
async def get_llm_config() -> LlmConfigResponse:
    """获取当前激活的 LLM 配置。"""
    cfg = llm_runtime.as_dict()
    return LlmConfigResponse(**cfg)


class LlmConfigUpdate(BaseModel):
    model: str | None = Field(None)
    base_url: str | None = Field(None)
    api_key: str | None = Field(None)
    temperature: float | None = Field(None, ge=0, le=2)


@router.put("/llm/config", response_model=LlmConfigResponse)
async def update_llm_config_compat(body: LlmConfigUpdate) -> LlmConfigResponse:
    """更新当前激活配置（兼容旧接口）。若尚无激活 profile 则自动创建。"""
    cfg = llm_runtime.as_dict()
    pid = cfg.get("active_profile_id", "")
    if pid:
        await llm_runtime.update_profile(
            profile_id=pid,
            model=body.model,
            base_url=body.base_url,
            api_key=body.api_key,
            temperature=body.temperature,
        )
    else:
        # 无激活 profile 时自动创建
        await llm_runtime.create_profile(
            name=body.model or "默认配置",
            model=body.model or "gpt-4o",
            base_url=body.base_url or "",
            api_key=body.api_key or "",
            temperature=body.temperature or 0.3,
        )
        # 激活它
        profiles = await llm_runtime.list_profiles()
        if profiles:
            await llm_runtime.activate(profiles[0].id)
    agent.reconfigure()
    await start_review_consumer()
    cfg = llm_runtime.as_dict()
    return LlmConfigResponse(**cfg)


# ── Profile CRUD ──

@router.get("/llm/profiles", response_model=list[ProfileResponse])
async def list_profiles() -> list[ProfileResponse]:
    """列出所有 LLM 配置。"""
    profiles = await llm_runtime.list_profiles()
    return [ProfileResponse(**p.__dict__) for p in profiles]


@router.post("/llm/profiles", response_model=ProfileResponse, status_code=201)
async def create_profile(body: ProfileCreate) -> ProfileResponse:
    """新建 LLM 配置。"""
    p = await llm_runtime.create_profile(
        name=body.name,
        model=body.model,
        base_url=body.base_url,
        api_key=body.api_key,
        temperature=body.temperature,
    )
    return ProfileResponse(**p.__dict__)


@router.put("/llm/profiles/{profile_id}", response_model=ProfileResponse)
async def update_profile(profile_id: str, body: ProfileUpdate) -> ProfileResponse:
    """更新指定配置的字段。"""
    try:
        p = await llm_runtime.update_profile(
            profile_id=profile_id,
            name=body.name,
            model=body.model,
            base_url=body.base_url,
            api_key=body.api_key,
            temperature=body.temperature,
        )
        if p.is_active:
            agent.reconfigure()
            await start_review_consumer()
        return ProfileResponse(**p.__dict__)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/llm/profiles/{profile_id}/activate", response_model=ProfileResponse)
async def activate_profile(profile_id: str) -> ProfileResponse:
    """切换激活指定配置并热切换 Agent 模型。"""
    try:
        p = await llm_runtime.activate(profile_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    agent.reconfigure()
    await start_review_consumer()
    return ProfileResponse(**p.__dict__)


@router.delete("/llm/profiles/{profile_id}")
async def delete_profile(profile_id: str) -> dict:
    """删除指定配置（不允许删除当前激活的）。"""
    try:
        await llm_runtime.delete_profile(profile_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True}
