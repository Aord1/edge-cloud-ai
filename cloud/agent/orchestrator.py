"""Agent 编排器 — LangGraph ReAct Agent，支持流式输出。"""

from __future__ import annotations

from collections.abc import AsyncIterator

from langgraph.prebuilt import create_react_agent

from .models import create_llm
from .prompts import SYSTEM_PROMPT
from .toolkit.registry import AGENT_TOOLS


class DefectAgent:
    """缺陷复核 Agent — 封装 LangGraph ReAct Agent 的创建与流式调用。"""

    def __init__(self) -> None:
        self._llm = create_llm()
        self._graph = create_react_agent(
            model=self._llm,
            tools=AGENT_TOOLS,
            prompt=SYSTEM_PROMPT,
        )

    async def stream(
        self, message: str, thread_id: str = "default"
    ) -> AsyncIterator[dict]:
        """流式执行 Agent，yield 每一步的事件。"""
        async for event in self._graph.astream_events(
            {"messages": [("user", message)]},
            config={"configurable": {"thread_id": thread_id}},
            version="v2",
        ):
            kind = event["event"]

            if kind == "on_chat_model_stream":
                chunk = event["data"]["chunk"]
                if chunk.content:
                    yield {"type": "text", "content": chunk.content}

            elif kind == "on_tool_start":
                name = event["name"]
                inputs = event["data"].get("input", {})
                yield {
                    "type": "tool_call",
                    "content": f"调用工具: {name}",
                    "tool_name": name,
                    "tool_input": inputs,
                }

            elif kind == "on_tool_end":
                output = event["data"].get("output", "")
                yield {"type": "tool_result", "content": str(output)}

        yield {"type": "done", "content": ""}


# 全局单例
agent = DefectAgent()
