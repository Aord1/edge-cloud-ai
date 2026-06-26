"""对话服务 — API 层与 Agent 层之间的服务抽象。

所有聊天相关的 API 路由必须通过本服务间接访问 Agent，
不允许跨层直接导入 agent 模块。
"""

from __future__ import annotations

from collections.abc import AsyncIterator


def _format_error(exc: Exception) -> str:
    try:
        body = getattr(exc, "body", None)
        if body and isinstance(body, dict):
            msg = body.get("message", "") or body.get("error", {}).get("message", "")
            if msg:
                return f"{type(exc).__name__}: {msg}"
    except Exception:
        pass
    status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    if status:
        return f"{type(exc).__name__} [HTTP {status}]: {exc}"
    cause = exc.__cause__ or exc.__context__
    if cause is not None:
        cause_msg = str(cause)
        if cause_msg and cause_msg != str(exc):
            return f"{type(exc).__name__}: {cause_msg}"
    return f"{type(exc).__name__}: {exc}"


async def stream_chat(message: str, thread_id: str = "default") -> AsyncIterator[dict]:
    """流式 AI 对话：封装 Agent 的流式调用。"""
    from ..agent import agent

    try:
        async for event in agent.stream(message, thread_id=thread_id):
            yield event
    except Exception as exc:
        detail = _format_error(exc)
        yield {"type": "text", "content": f"[调用失败] {detail}"}
        yield {"type": "done", "content": ""}
