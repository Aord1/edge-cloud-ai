"""对话服务 — API 层与 Agent 层之间的服务抽象。

所有聊天相关的 API 路由必须通过本服务间接访问 Agent，
不允许跨层直接导入 agent 模块。
"""

from __future__ import annotations

from collections.abc import AsyncIterator


async def stream_chat(message: str, thread_id: str = "default") -> AsyncIterator[dict]:
    """流式 AI 对话：封装 Agent 的流式调用。

    服务层的职责：
    - 隔离 API 层与 Agent 层的直接依赖
    - 统一注入上下文（thread_id 管理、系统提示词追加等）
    - 统一错误兜底（Agent 异常时返回可读的错误事件）
    - 为后续扩展（限流、日志、审计）预留接入点
    """
    from ..agent import agent

    try:
        async for event in agent.stream(message, thread_id=thread_id):
            yield event
    except Exception as exc:
        yield {
            "type": "text",
            "content": f"[服务异常] Agent 调用失败: {exc}",
        }
        yield {
            "type": "done",
            "content": "",
        }
