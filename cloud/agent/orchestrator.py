"""Agent 编排器 — LangGraph ReAct Agent，支持流式输出（多模态：文本+图片）。"""

from __future__ import annotations

import base64
from collections.abc import AsyncIterator
from pathlib import Path

from langchain_core.messages import HumanMessage
from langgraph.prebuilt import create_react_agent

from .models import create_llm
from .prompts import SYSTEM_PROMPT
from .toolkit.registry import AGENT_TOOLS
from .llm_config import llm_runtime


class DefectAgent:
    """缺陷复核 Agent — 封装 LangGraph ReAct Agent 的创建与流式调用。"""

    def __init__(self) -> None:
        self._llm = create_llm()
        self._graph = create_react_agent(
            model=self._llm,
            tools=AGENT_TOOLS,
            prompt=SYSTEM_PROMPT,
        )

    def reconfigure(self) -> None:
        """根据最新运行时配置重建 Agent 图（热切换模型）。"""
        self._llm = create_llm()
        self._graph = create_react_agent(
            model=self._llm,
            tools=AGENT_TOOLS,
            prompt=SYSTEM_PROMPT,
        )
        print(f"[Agent] 已切换模型: {llm_runtime.model}")

    async def stream(
        self, message: str, thread_id: str = "default"
    ) -> AsyncIterator[dict]:
        """流式执行 Agent（纯文本），yield 每一步的事件。"""
        async for event in self._stream_events(
            {"messages": [("user", message)]}, thread_id
        ):
            yield event

    async def stream_with_image(
        self,
        text: str,
        image_path: str = "",
        image_b64: str = "",
        thread_id: str = "default",
    ) -> AsyncIterator[dict]:
        """流式执行 Agent（多模态：文本 + 图片），yield 每一步的事件。"""
        content: list[dict] = [{"type": "text", "text": text}]

        if image_path:
            raw = Path(image_path).read_bytes()
            image_b64 = base64.b64encode(raw).decode()

        if image_b64:
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
            })

        message = HumanMessage(content=content)
        async for event in self._stream_events(
            {"messages": [message]}, thread_id
        ):
            yield event

    async def _stream_events(
        self, input_data: dict, thread_id: str
    ) -> AsyncIterator[dict]:
        """内部流式执行，解析事件并 yield。若流式无文本输出则降级为非流式。"""
        final_content = ""
        had_text = False
        async for event in self._graph.astream_events(
            input_data,
            config={"configurable": {"thread_id": thread_id}},
            version="v2",
        ):
            kind = event["event"]

            if kind == "on_chat_model_stream":
                chunk = event["data"]["chunk"]
                if chunk.content:
                    had_text = True
                    final_content += chunk.content
                    yield {"type": "text", "content": chunk.content}

            elif kind == "on_chat_model_end":
                output = event["data"].get("output", None)
                if output and hasattr(output, "content") and output.content:
                    if isinstance(output.content, str):
                        final_content = output.content
                    elif isinstance(output.content, list):
                        final_content = next((c.get("text", "") for c in output.content if c.get("type") == "text"), "")

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

        # 流式无文本 → 降级非流式
        if not had_text and not final_content:
            try:
                msg = await self._llm.ainvoke(input_data["messages"])
                if msg and hasattr(msg, "content") and msg.content:
                    final_content = msg.content if isinstance(msg.content, str) else str(msg.content)
                    yield {"type": "text", "content": final_content}
            except Exception:
                pass

        if final_content:
            yield {"type": "text", "content": ""}
        yield {"type": "done", "content": final_content}


# 全局单例
agent = DefectAgent()
