"""缺陷详情查询工具。"""

from datetime import timedelta, timezone
from uuid import UUID

from ...db.models import DetectionLog
from .base import AgentBaseTool


class GetDefectDetail(AgentBaseTool):
    name: str = "get_defect_detail"
    description: str = (
        "查询指定检测记录的详细信息，包括每个缺陷的类别、置信度和位置。"
        "Args: detection_id (检测记录UUID)"
    )

    async def _arun(self, detection_id: str) -> str:
        try:
            uid = UUID(detection_id)
        except ValueError:
            return f"无效的记录 ID: {detection_id}"

        async with self.get_db() as db:
            row = await db.get(DetectionLog, uid)

        if not row:
            return f"未找到记录 {detection_id}"

        tz = timezone(timedelta(hours=8))
        ts = row.created_at.astimezone(tz).strftime("%Y-%m-%d %H:%M:%S")
        lines = [
            f"记录 {detection_id}:",
            f"  设备: {row.device_id}",
            f"  时间: {ts}",
            f"  原因: {row.reason}",
            f"  推理耗时: {row.inference_ms}ms",
            f"  平均置信度: {row.avg_confidence:.2f}",
        ]
        dets = row.detections if isinstance(row.detections, list) else []
        if dets:
            lines.append(f"  缺陷详情 ({len(dets)} 个):")
            for i, d in enumerate(dets):
                if isinstance(d, dict):
                    cls = d.get("class_name", "unknown")
                    conf = d.get("confidence", 0)
                    bbox = d.get("bbox", [])
                    lines.append(f"    {i + 1}. {cls} 置信度{conf:.2f} bbox={bbox}")
        return "\n".join(lines)

    def _run(self, detection_id: str) -> str:
        raise NotImplementedError("Use _arun")


get_defect_detail = GetDefectDetail()