"""检测数据上传接口 — 含自动 Agent 复核。"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, UploadFile, File, Form
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..api.deps import get_db
from ..config import settings
from ..db.models import DetectionLog
from ..db.session import AsyncSessionLocal
from ..schemas.detection import DetectionUploadResponse

router = APIRouter(prefix="/api/v1", tags=["detection"])

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

# ── Agent 复核队列（单消费者，避免并发雪崩）──

_review_queue: asyncio.Queue[uuid.UUID] = asyncio.Queue(maxsize=settings.review_queue_maxsize)
_queued_ids: set[uuid.UUID] = set()
_consumer_started = False


async def _start_review_consumer() -> None:
    """后台启动一次，全局单例。"""
    global _consumer_started
    if _consumer_started:
        return
    _consumer_started = True
    asyncio.create_task(_review_consumer())


async def _review_consumer() -> None:
    """串行消费队列中的复核请求，避免同时发起大量 LLM 调用。"""
    print("[ReviewQueue] 消费者启动")
    while True:
        defect_id = await _review_queue.get()
        _queued_ids.discard(defect_id)
        try:
            await _do_review(defect_id)
        except Exception as e:
            print(f"[ReviewQueue] 复核失败 {defect_id}: {e}")
        _review_queue.task_done()
        # 间隔 N 秒，避免速率过高
        await asyncio.sleep(settings.review_consumer_interval)


def _enqueue_review(defect_id: uuid.UUID) -> None:
    if defect_id not in _queued_ids:
        _queued_ids.add(defect_id)
        try:
            _review_queue.put_nowait(defect_id)
        except asyncio.QueueFull:
            pass  # 队列满则丢弃（太多待复核）


# ── 路由 ──

@router.post("/detect/upload", response_model=DetectionUploadResponse)
async def upload_detection(
    device_id: str = Form(...),
    reason: str = Form(...),
    detections: str = Form(...),
    avg_confidence: float = Form(...),
    inference_ms: float = Form(...),
    timestamp: float = Form(...),
    image: UploadFile = File(None),
    db: AsyncSession = Depends(get_db),
) -> DetectionUploadResponse:
    dets = json.loads(detections)

    image_path = None
    if image and image.filename:
        fname = f"{uuid.uuid4().hex}_{image.filename}"
        filepath = UPLOAD_DIR / fname
        filepath.write_bytes(await image.read())
        image_path = str(filepath)

    log = DetectionLog(
        device_id=device_id,
        reason=reason,
        detections=dets,
        image_path=image_path,
        avg_confidence=avg_confidence,
        inference_ms=inference_ms,
    )
    db.add(log)
    await db.flush()

    # 入队（单消费者串行处理，不会堆叠）
    _enqueue_review(log.id)

    return DetectionUploadResponse(
        id=log.id,
        message=f"已接收 {len(dets)} 条检测结果",
    )


async def _do_review(defect_id: uuid.UUID) -> None:
    """实际执行一条 Agent 复核（由消费者串行调用）。"""
    from ..agent import agent

    # 读取记录内容
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(DetectionLog).where(DetectionLog.id == defect_id)
        )
        log_entry = result.scalar_one_or_none()
        if not log_entry:
            return
        dets = log_entry.detections
        device_id = log_entry.device_id
        reason = log_entry.reason

    defect_types = ", ".join(set(d.get("class_name", "?") for d in dets))
    confs = ", ".join(f"{d.get('class_name','?')}:{d.get('confidence',0):.2f}" for d in dets)
    prompt = (
        f"请复核以下钢材表面缺陷:\n"
        f"设备: {device_id}\n"
        f"原因: {reason}\n"
        f"缺陷: {defect_types}\n"
        f"置信度: {confs}\n"
        f"请给出判定结论和处理建议。"
    )

    full_text = []
    tool_calls = []
    try:
        async for event in agent.stream(prompt, thread_id=str(defect_id)):
            if event["type"] == "text":
                full_text.append(event["content"])
            elif event["type"] == "tool_call":
                tool_calls.append({
                    "tool": event.get("tool_name", ""),
                    "input": str(event.get("tool_input", "")),
                })
    except Exception as e:
        full_text.append(f"[Agent 调用失败: {e}]")

    review = {
        "verdict": "",
        "reasoning": "".join(full_text),
        "tool_calls": tool_calls,
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
    }

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(DetectionLog).where(DetectionLog.id == defect_id)
        )
        log_entry = result.scalar_one_or_none()
        if log_entry:
            log_entry.agent_review = review
            await session.commit()
            print(f"[Review] {str(defect_id)[:8]} 复核完成")
