"""RAG 知识库 — 检索 + 重排序。

流程：query → embed → pgvector 召回 top-N → CrossEncoder 重排序 → 返回 top-K。
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..db.models import QualityStandard
from .embedding import embed_text

logger = logging.getLogger(__name__)


@dataclass
class RetrievalResult:
    category: str
    title: str
    content: str
    source: str | None
    score: float


async def retrieve(
    session: AsyncSession,
    query: str,
    top_k: int | None = None,
) -> list[RetrievalResult]:
    top_k = top_k or settings.rag_top_k
    retrieve_n = settings.rag_retrieve_n

    query_vec = await embed_text(query)

    stmt = (
        select(
            QualityStandard.category,
            QualityStandard.title,
            QualityStandard.content,
            QualityStandard.source,
            QualityStandard.embedding.cosine_distance(query_vec).label("distance"),
        )
        .order_by(text("distance ASC"))
        .limit(retrieve_n)
    )
    result = await session.execute(stmt)
    candidates = result.all()

    if not candidates:
        return []

    if len(candidates) == 1:
        row = candidates[0]
        score = 1.0 - row.distance
        if score < settings.rag_similarity_threshold:
            return []
        return [RetrievalResult(
            category=row.category, title=row.title,
            content=row.content, source=row.source, score=score,
        )]

    # 直接用 cosine 距离排序（跳过 CrossEncoder 重排序，避免下载大模型）
    ranked: list[RetrievalResult] = []
    for row in candidates:
        score = 1.0 - row.distance
        if score >= settings.rag_similarity_threshold:
            ranked.append(RetrievalResult(
                category=row.category, title=row.title,
                content=row.content, source=row.source, score=score,
            ))
    ranked.sort(key=lambda r: r.score, reverse=True)
    return ranked[:top_k]