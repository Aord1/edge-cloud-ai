"""RAG 知识库 — Ingest 入库，切分文档 → 生成 embedding → 写入 quality_standards 表。"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import QualityStandard
from .embedding import embed_texts
from .splitter import Chunk, split_by_entries

logger = logging.getLogger(__name__)


async def ingest(
    session: AsyncSession,
    entries: list[dict],
    batch_size: int = 32,
) -> int:
    chunks = split_by_entries(entries)
    if not chunks:
        logger.warning("No chunks produced from %d entries", len(entries))
        return 0

    await _dedup(session, chunks)

    inserted = 0
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i : i + batch_size]
        texts = [c.content for c in batch]
        vectors = await embed_texts(texts)

        for chunk, vec in zip(batch, vectors):
            session.add(QualityStandard(
                category=chunk.category,
                title=chunk.title,
                content=chunk.content,
                source=chunk.source,
                embedding=vec,
            ))
            inserted += 1

    await session.commit()
    logger.info("Ingested %d chunks into quality_standards", inserted)
    return inserted


async def _dedup(session: AsyncSession, chunks: list[Chunk]) -> None:
    seen: set[str] = set()
    to_remove: list[Chunk] = []

    for chunk in chunks:
        key = f"{chunk.category}::{chunk.title}"
        if key in seen:
            to_remove.append(chunk)
        seen.add(key)

    for chunk in to_remove:
        stmt = select(QualityStandard).where(
            QualityStandard.category == chunk.category,
            QualityStandard.title == chunk.title,
        )
        result = await session.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing:
            await session.delete(existing)

    if to_remove:
        await session.flush()

    unique: list[Chunk] = []
    seen2: set[str] = set()
    for chunk in chunks:
        key = f"{chunk.category}::{chunk.title}"
        if key not in seen2:
            unique.append(chunk)
            seen2.add(key)
    chunks[:] = unique