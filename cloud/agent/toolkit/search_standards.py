"""质检标准检索工具 — Agent 通过自然语言查询相关知识库条目。"""

from ...rag.retriever import retrieve
from .base import AgentBaseTool


class SearchStandards(AgentBaseTool):
    name: str = "search_standards"
    description: str = (
        "从知识库检索与查询相关的质检标准条目。支持语义匹配，可用自然语言描述问题。"
        "Args: query (自然语言查询如'裂纹深度超过多少需要标记'), top_k (返回条数默认3)"
    )

    async def _arun(self, query: str, top_k: int = 3) -> str:
        async with self.get_db() as db:
            results = await retrieve(db, query, top_k=top_k)

        if not results:
            return "未找到与查询相关的质检标准。"

        lines = [f"找到 {len(results)} 条相关标准："]
        for i, r in enumerate(results, 1):
            src = f"（来源：{r.source}）" if r.source else ""
            lines.append(f"  {i}. [{r.category}] {r.title} {src}")
            lines.append(f"     {r.content}")
            lines.append(f"     相关度：{r.score:.3f}")
        return "\n".join(lines)

    def _run(self, query: str, top_k: int = 3) -> str:
        raise NotImplementedError("Use _arun")


search_standards = SearchStandards()