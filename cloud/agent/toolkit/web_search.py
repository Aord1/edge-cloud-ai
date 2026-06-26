"""联网搜索工具 — Agent 通过 Tavily API 搜索互联网获取最新信息。"""

from tavily import TavilyClient

from ...config import settings
from .base import AgentBaseTool


class WebSearch(AgentBaseTool):
    name: str = "web_search"
    description: str = (
        "搜索互联网获取与查询相关的最新信息，用于补充知识库之外的行业标准、"
        "最新工艺要求和政策法规等。"
        "Args: query (搜索查询文本), max_results (返回条数, 默认5)"
    )

    async def _arun(self, query: str, max_results: int = 5) -> str:
        try:
            client = TavilyClient(api_key=settings.tavily_api_key)
            response = client.search(
                query=query,
                search_depth="advanced",
                max_results=max_results,
                include_answer=True,
            )
        except Exception as e:
            return f"网络搜索失败: {e}"

        if not response.get("results"):
            answer = response.get("answer", "")
            if answer:
                return f"未找到网页结果，综合回答：\n{answer}"
            return f"未找到与「{query}」相关的结果。"

        lines = [f"搜索「{query}」找到 {len(response['results'])} 条结果："]
        answer = response.get("answer", "")
        if answer:
            lines.append(f"\n摘要：{answer}\n")

        for i, r in enumerate(response["results"], 1):
            title = r.get("title", "无标题")
            url = r.get("url", "")
            content = r.get("content", "")
            lines.append(f"  {i}. {title}")
            lines.append(f"     URL: {url}")
            lines.append(f"     {content[:300]}")
            lines.append("")

        return "\n".join(lines)

    def _run(self, query: str, max_results: int = 5) -> str:
        raise NotImplementedError("Use _arun")


web_search = WebSearch()
