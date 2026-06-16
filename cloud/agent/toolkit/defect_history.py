"""缺陷历史查询工具。"""

from datetime import timedelta, timezone

from sqlalchemy import select

from ...db.models import DetectionLog
from .base import AgentBaseTool


class QueryDefectHistory(AgentBaseTool):
    name: str = "query_defect_history"
    description: str = (
        "查询指定设备的最近缺陷检测记录。"
        "Args: device_id (设备ID如camera-01), limit (返回条数默认10)"
    )

    async def _arun(self, device_id: str, limit: int = 10) -> str:
        async with self.get_db() as db:
            stmt = (
                select(DetectionLog)
                .where(DetectionLog.device_id == device_id)
                .order_by(DetectionLog.created_at.desc())
                .limit(limit)
            )
            result = await db.execute(stmt)
            rows = result.scalars().all()

        if not rows:
            return f"设备 {device_id} 暂无缺陷记录。"

        tz = timezone(timedelta(hours=8))
        lines = [f"设备 {device_id} 最近 {len(rows)} 条缺陷记录："]
        for r in rows:
            ts = r.created_at.astimezone(tz).strftime("%m-%d %H:%M")
            det_count = len(r.detections) if isinstance(r.detections, list) else 0
            avg_conf = r.avg_confidence or 0
            reason = r.reason or "unknown"
            lines.append(
                f"  [{r.id}] {ts} | {reason} | {det_count}个缺陷 | 均置信度{avg_conf:.2f}"
            )
        return "\n".join(lines)

    def _run(self, device_id: str, limit: int = 10) -> str:
        raise NotImplementedError("Use _arun")


query_defect_history = QueryDefectHistory()