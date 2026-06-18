"""质检报告生成工具 — 根据检测记录生成结构化复核报告。"""

from datetime import timedelta, timezone
from uuid import UUID

from langchain_core.tools import tool

from ...db.models import DetectionLog
from ...db.session import AsyncSessionLocal

TZ = timezone(timedelta(hours=8))

CLASS_CN = {
    "crazing": "裂纹", "inclusion": "夹杂", "patches": "斑块",
    "pitted_surface": "麻点", "rolled_in_scale": "氧化皮", "scratches": "划痕",
    "rolled-in_scale": "氧化皮",
}


@tool
async def generate_report(detection_id: str) -> str:
    """根据检测记录生成结构化的缺陷复核报告，包含判定结论、依据和处置建议。

    Args:
        detection_id: 检测记录 UUID
    """
    try:
        uid = UUID(detection_id)
    except ValueError:
        return f"无效的记录 ID: {detection_id}"

    async with AsyncSessionLocal() as db:
        row = await db.get(DetectionLog, uid)

    if not row:
        return f"未找到记录 {detection_id}"

    ts = row.created_at.astimezone(TZ).strftime("%Y-%m-%d %H:%M:%S")
    dets = row.detections if isinstance(row.detections, list) else []
    defect_types = ", ".join(set(
        CLASS_CN.get(d.get("class_name", ""), d.get("class_name", "?"))
        for d in dets
    ))

    lines = [
        "=" * 50,
        "          质检报告",
        "=" * 50,
        "",
        f"报告编号: {detection_id}",
        f"设备编号: {row.device_id}",
        f"检测时间: {ts}",
        f"推理耗时: {row.inference_ms:.0f}ms",
        f"平均置信度: {row.avg_confidence:.2f}",
        "",
        "── 缺陷信息 ──",
        f"缺陷类型: {defect_types}",
        f"缺陷数量: {len(dets)} 处",
        f"检测原因: {row.reason}",
        f"分流决策: {'云端复核' if row.decision == 'CLOUD' else '本地判定'}",
    ]

    if dets:
        lines.append("")
        lines.append("缺陷详情:")
        for i, d in enumerate(dets, 1):
            if isinstance(d, dict):
                cn = CLASS_CN.get(d.get("class_name", ""), d.get("class_name", "?"))
                conf = d.get("confidence", 0)
                bbox = d.get("bbox", [])
                lines.append(f"  {i}. {cn}  置信度 {conf:.2f}  位置 {bbox}")

    review = row.agent_review
    if review and isinstance(review, dict):
        verdict = review.get("verdict", "")
        reasoning = review.get("reasoning", "")
        recommendation = review.get("recommendation", "")

        lines.append("")
        lines.append("── Agent 复核结论 ──")
        if verdict:
            lines.append(f"判定结果: {verdict}")
        if reasoning and not reasoning.startswith("[") and not reasoning.startswith("="):
            lines.append(f"判定依据: {reasoning}")
        if recommendation:
            lines.append(f"处置建议: {recommendation}")
    else:
        lines.append("")
        lines.append("── 状态 ──")
        lines.append("尚未完成 Agent 复核")

    lines.append("")
    lines.append("=" * 50)
    return "\n".join(lines)
