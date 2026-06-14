"""AI 缺陷复核对话 API — SSE 流式。"""

from __future__ import annotations

import json

from fastapi import APIRouter, Body, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..agent import agent

router = APIRouter(prefix="/api/v1", tags=["chat"])


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="用户消息")
    thread_id: str = Field(default="default", description="会话 ID")


@router.post("/chat")
async def chat(body: ChatRequest, request: Request):
    """流式 AI 缺陷复核对话。

    返回 SSE 流，每帧格式: data: {"type":"text"|"tool_call"|"tool_result"|"done","content":"..."}
    """

    async def _stream():
        async for event in agent.stream(body.message, thread_id=body.thread_id):
            if await request.is_disconnected():
                break
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )