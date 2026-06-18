"""检测数据处理服务 — HTTP 和 MQTT 共用。"""

from __future__ import annotations

import asyncio
import base64
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

from ..config import settings
from ..db.models import DefectReview, DetectionLog
from ..db.session import AsyncSessionLocal
from ..agent.llm_config import llm_runtime

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

_review_queue: asyncio.Queue[uuid.UUID] = asyncio.Queue(maxsize=settings.review_queue_maxsize)
_queued_ids: set[uuid.UUID] = set()
_consumer_started = False


async def start_review_consumer() -> None:
    global _consumer_started
    if _consumer_started:
        return
    _consumer_started = True
    asyncio.create_task(_review_consumer())


def enqueue_review(defect_id: uuid.UUID) -> None:
    if defect_id not in _queued_ids:
        _queued_ids.add(defect_id)
        try:
            _review_queue.put_nowait(defect_id)
        except asyncio.QueueFull:
            pass


async def process_upload(
    device_id: str,
    reason: str,
    detections: list[dict],
    avg_confidence: float,
    inference_ms: float,
    image_b64: str = "",
    decision: str = "CLOUD",
) -> DetectionLog:
    image_path = None
    if image_b64:
        try:
            raw = base64.b64decode(image_b64)
            fname = f"{uuid.uuid4().hex}.jpg"
            filepath = UPLOAD_DIR / fname
            filepath.write_bytes(raw)
            image_path = str(filepath)
        except Exception:
            pass

    log = DetectionLog(
        device_id=device_id,
        reason=reason,
        decision=decision,
        detections=detections,
        image_path=image_path,
        avg_confidence=avg_confidence,
        inference_ms=inference_ms,
    )

    async with AsyncSessionLocal() as session:
        session.add(log)
        await session.commit()

    if decision == "CLOUD":
        enqueue_review(log.id)
    return log


async def _review_consumer() -> None:
    print("[ReviewQueue] 消费者启动")
    while True:
        defect_id = await _review_queue.get()
        _queued_ids.discard(defect_id)
        if not llm_runtime.api_key:
            print("[ReviewQueue] LLM 未配置，跳过复核")
            await _write_review(defect_id, reasoning="[未配置 API Key] 请在界面右上角 🤖 配置 LLM 密钥后再试。")
        else:
            try:
                await _do_review(defect_id)
            except Exception as e:
                print(f"[ReviewQueue] 复核失败 {defect_id}: {e}")
                import traceback; traceback.print_exc()
                await _write_review(defect_id, reasoning=f"[Agent 调用失败] {e}")
        _review_queue.task_done()
        await asyncio.sleep(settings.review_consumer_interval)


async def _write_review(defect_id: uuid.UUID, reasoning: str) -> None:
    now = datetime.now(timezone.utc)
    review = {
        "verdict": "",
        "reasoning": reasoning,
        "tool_calls": [],
        "reviewed_at": now.isoformat(),
    }
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(DetectionLog).where(DetectionLog.id == defect_id)
        )
        log_entry = result.scalar_one_or_none()
        if log_entry:
            log_entry.agent_review = review
            defect_review = DefectReview(
                defect_log_id=defect_id,
                verdict="",
                reasoning_chain={},
                tool_calls=[],
                reviewed_by=llm_runtime.model or "(未配置)",
                reviewed_at=now,
            )
            session.add(defect_review)
            await session.commit()


async def _do_review(defect_id: uuid.UUID) -> None:
    from ..agent import agent

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
        image_path = log_entry.image_path

    defect_types = ", ".join(set(d.get("class_name", "?") for d in dets))
    confs = ", ".join(f"{d.get('class_name','?')}:{d.get('confidence',0):.2f}" for d in dets)
    prompt = (
        f"请复核以下钢材表面缺陷（附缺陷图片）:\n"
        f"设备: {device_id}\n"
        f"原因: {reason}\n"
        f"缺陷: {defect_types}\n"
        f"置信度: {confs}\n\n"
        f"请按以下格式给出结构化复核报告：\n"
        f"【判定结论】合格 / 次品 / 待确认（三选一）\n"
        f"【判定依据】结合图片分析、缺陷特征和质检标准，说明判定理由\n"
        f"【处置建议】放行 / 返工 / 报废 / 调整工艺参数\n\n"
        f"要求：可利用 search_standards 检索质检标准，用 query_defect_history 查历史案例。"
    )

    full_text = []
    tool_calls = []
    done_text = ""
    try:
        async for event in agent.stream_with_image(
            prompt, image_path=image_path or "", thread_id=str(defect_id)
        ):
            if event["type"] == "text":
                full_text.append(event["content"])
            elif event["type"] == "tool_call":
                tool_calls.append({
                    "tool": event.get("tool_name", ""),
                    "input": str(event.get("tool_input", "")),
                })
            elif event["type"] == "done":
                done_text = event.get("content", "")
    except Exception as e:
        return await _write_review(defect_id, reasoning=f"[Agent 调用失败] {e}")

    reasoning = "".join(full_text) or done_text
    if not reasoning:
        reasoning = f"[Agent 无输出] 模型 {llm_runtime.model} 未返回有效内容，请检查模型和 API Key 配置。"

    verdict = _extract_field(reasoning, "判定结论")
    recommendation = _extract_field(reasoning, "处置建议")
    if not verdict and reasoning and not reasoning.startswith("["):
        verdict = "复核完成"

    now = datetime.now(timezone.utc)

    review = {
        "verdict": verdict,
        "reasoning": reasoning,
        "recommendation": recommendation,
        "tool_calls": tool_calls,
        "reviewed_by": llm_runtime.model,
        "reviewed_at": now.isoformat(),
    }

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(DetectionLog).where(DetectionLog.id == defect_id)
        )
        log_entry = result.scalar_one_or_none()
        if log_entry:
            log_entry.agent_review = review

            defect_review = DefectReview(
                defect_log_id=defect_id,
                verdict=verdict,
                reasoning_chain={"steps": tool_calls} if tool_calls else {},
                tool_calls=[{"tool": t["tool"], "input": t["input"]} for t in tool_calls],
                reviewed_by=llm_runtime.model,
                reviewed_at=now,
            )
            session.add(defect_review)

            await session.commit()
            print(f"[Review] {str(defect_id)[:8]} 复核完成")


def _extract_field(text: str, field: str) -> str:
    """从结构化 Agent 输出中提取字段值。
    格式: 【字段名】值（到下一个【或行尾）"""
    import re
    pattern = rf"【{field}】\s*(.+?)(?=\n【|\n*$)"
    m = re.search(pattern, text)
    if m:
        value = m.group(1).strip()
        return value.replace("（", "(").replace("）", ")")
    return ""
