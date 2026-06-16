"""RAG 知识库 — 文档切分，将原始文本拆成可嵌入的片段。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Chunk:
    category: str
    title: str
    content: str
    source: str | None = None


def split_by_entries(entries: list[dict]) -> list[Chunk]:
    chunks: list[Chunk] = []
    for entry in entries:
        text = entry.get("content", "")
        if not text:
            continue
        max_len = 500
        if len(text) <= max_len:
            chunks.append(Chunk(
                category=entry["category"],
                title=entry["title"],
                content=text,
                source=entry.get("source"),
            ))
        else:
            sentences = _split_sentences(text)
            buf = ""
            for sent in sentences:
                if len(buf) + len(sent) > max_len and buf:
                    chunks.append(Chunk(
                        category=entry["category"],
                        title=f"{entry['title']} (续)",
                        content=buf.strip(),
                        source=entry.get("source"),
                    ))
                    buf = sent
                else:
                    buf += sent if not buf else "" + sent
            if buf.strip():
                chunks.append(Chunk(
                    category=entry["category"],
                    title=entry["title"],
                    content=buf.strip(),
                    source=entry.get("source"),
                ))
    return chunks


def _split_sentences(text: str) -> list[str]:
    sentences = []
    buf = ""
    for ch in text:
        buf += ch
        if ch in ("。", "；", "！", "？", ".", ";", "!", "?"):
            sentences.append(buf)
            buf = ""
    if buf:
        sentences.append(buf)
    return [s.strip() for s in sentences if s.strip()]