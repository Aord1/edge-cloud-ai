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
from ..db.models import DetectionLog
from ..db.session import AsyncSessionLocal
from ..schemas.detection import DetectionUploadResponse

router = APIRouter(prefix="/api/v1", tags=["detection"])

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)


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

    # 自动触发 Agent 复核（后台运行，不阻塞响应）
    defect_id = log.id
    asyncio.create_task(_auto_review(defect_id, dets, device_id, reason))

    return DetectionUploadResponse(
        id=defect_id,
        message=f"已接收 {len(dets)} 条检测结果，Agent 复核中...",
    )


async def _auto_review(defect_id: uuid.UUID, dets: list, device_id: str,
                       reason: str) -> None:
    """后台任务：调用 Agent 复核缺陷，结果写入 DB。"""
    try:
        from ..agent import agent

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
        async for event in agent.stream(prompt, thread_id=str(defect_id)):
            if event["type"] == "text":
                full_text.append(event["content"])
            elif event["type"] == "tool_call":
                tool_calls.append({
                    "tool": event.get("tool_name", ""),
                    "input": str(event.get("tool_input", "")),
                })

        review = {
            "verdict": "",
            "reasoning": "".join(full_text),
            "tool_calls": tool_calls,
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
        }

        # 写入 DB（独立 session）
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(DetectionLog).where(DetectionLog.id == defect_id)
            )
            log_entry = result.scalar_one_or_none()
            if log_entry:
                log_entry.agent_review = review
                await session.commit()
                print(f"[AutoReview] {defect_id} 复核完成")

    except Exception as e:
        print(f"[AutoReview] {defect_id} 复核失败: {e}")
