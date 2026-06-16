"""RAG 知识库 — 嵌入服务，异步封装 sentence-transformers。"""

from __future__ import annotations

import asyncio
import logging

from sentence_transformers import SentenceTransformer

from ..config import settings

logger = logging.getLogger(__name__)

_model: SentenceTransformer | None = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        logger.info("Loading embedding model: %s", settings.embedding_model_id)
        _model = SentenceTransformer(settings.embedding_model_id)
    return _model


async def embed_text(text: str) -> list[float]:
    model = _get_model()
    return (await asyncio.to_thread(model.encode, text, normalize_embeddings=True)).tolist()


async def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    model = _get_model()
    return (await asyncio.to_thread(model.encode, texts, normalize_embeddings=True)).tolist()