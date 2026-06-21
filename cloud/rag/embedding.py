"""RAG 知识库 — 嵌入服务，异步封装 sentence-transformers。"""

from __future__ import annotations

import asyncio
import logging
import os
import threading

# 国内环境自动使用 HF 镜像（必须在 import sentence_transformers 之前设置）
if not os.environ.get("HF_ENDPOINT"):
    os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

from sentence_transformers import SentenceTransformer

from ..config import settings

logger = logging.getLogger(__name__)

_model: SentenceTransformer | None = None
_lock = threading.Lock()


def _get_model() -> SentenceTransformer:
    global _model
    if _model is not None:
        return _model
    with _lock:
        if _model is not None:
            return _model
        logger.info("Loading embedding model: %s", settings.embedding_model_id)
        _model = SentenceTransformer(settings.embedding_model_id)
        logger.info("Embedding model loaded")
        return _model


async def embed_text(text: str) -> list[float]:
    model = await asyncio.to_thread(_get_model)
    return (await asyncio.to_thread(model.encode, text, normalize_embeddings=True)).tolist()


async def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    model = await asyncio.to_thread(_get_model)
    return (await asyncio.to_thread(model.encode, texts, normalize_embeddings=True)).tolist()