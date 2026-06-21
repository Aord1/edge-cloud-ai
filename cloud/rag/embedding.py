"""RAG 知识库 — 嵌入服务，支持本地模型 / 远程 API 两种模式。

默认使用远程 API（兼容 OpenAI Embeddings 协议，如硅基流动），
无需下载 2GB+ 的本地模型。设置 EMBEDDING_MODE=local 可切换回本地。
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
from typing import Any

import httpx

from ..config import settings

logger = logging.getLogger(__name__)

# ── 远程 API 模式 ──

_http_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(timeout=30)
    return _http_client


async def _embed_remote(texts: list[str]) -> list[list[float]]:
    """通过 OpenAI 兼容 Embeddings API 获取向量。"""
    client = _get_client()
    base = settings.embedding_api_url or "https://api.siliconflow.cn/v1"
    api_key = settings.embedding_api_key
    if not api_key:
        from ..agent.llm_config import llm_runtime
        api_key = llm_runtime.api_key
    url = f"{base.rstrip('/')}/embeddings"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload: dict[str, Any] = {
        "model": settings.embedding_model_id,
        "input": texts,
        "encoding_format": "float",
    }
    resp = await client.post(url, json=payload, headers=headers)
    resp.raise_for_status()
    data = resp.json()
    return [item["embedding"] for item in data["data"]]


# ── 本地模式 ──

if not os.environ.get("HF_ENDPOINT"):
    os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

_local_model: Any = None
_lock = threading.Lock()


def _get_local_model() -> Any:
    global _local_model
    if _local_model is not None:
        return _local_model
    with _lock:
        if _local_model is not None:
            return _local_model
        from sentence_transformers import SentenceTransformer
        logger.info("Loading local embedding model: %s", settings.embedding_model_id)
        _local_model = SentenceTransformer(settings.embedding_model_id)
        return _local_model


async def _embed_local(texts: list[str]) -> list[list[float]]:
    model = await asyncio.to_thread(_get_local_model)
    result = await asyncio.to_thread(model.encode, texts, normalize_embeddings=True)
    return result.tolist()


# ── 公共接口 ──

_use_local: bool | None = None


def _is_local() -> bool:
    global _use_local
    if _use_local is None:
        _use_local = os.environ.get("EMBEDDING_MODE", "").lower() == "local"
    return _use_local


async def embed_text(text: str) -> list[float]:
    results = await embed_texts([text])
    return results[0]


async def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    if _is_local():
        return await _embed_local(texts)
    else:
        return await _embed_remote(texts)
