"""缺陷统计工具。"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from ...db.models import DetectionLog
from .base import AgentBaseTool


class QueryDefectStats(AgentBaseTool):
    name: str = "query_defect_stats"
    description: str = (
        "查询指定设备在最近N小时内的缺陷统计。"
        "Args: device_id (设备ID如camera-01), hours (统计时间范围默认24)"
    )

    async def _arun(self, device_id: str, hours: int = 24) -> str:
        tz = timezone(timedelta(hours=8))
        since = datetime.now(tz=tz) - timedelta(hours=hours)

        async with self.get_db() as db:
            stmt = (
                select(DetectionLog)
                .where(
                    DetectionLog.device_id == device_id,
                    DetectionLog.created_at >= since,
                )
                .order_by(DetectionLog.created_at.desc())
            )
            result = await db.execute(stmt)
            rows = result.scalars().all()

        if not rows:
            return f"设备 {device_id} 最近 {hours} 小时内无缺陷记录。"

        total = len(rows)
        type_counts: dict[str, int] = {}
        conf_sum = 0.0
        for r in rows:
            conf_sum += r.avg_confidence or 0
            dets = r.detections if isinstance(r.detections, list) else []
            for d in dets:
                if isinstance(d, dict):
                    name = d.get("class_name", "unknown")
                    type_counts[name] = type_counts.get(name, 0) + 1

        avg_conf = conf_sum / total if total > 0 else 0
        lines = [
            f"设备 {device_id} 最近 {hours} 小时统计：",
            f"  总记录数: {total}",
            f"  平均置信度: {avg_conf:.2f}",
        ]
        if type_counts:
            lines.append("  缺陷类型分布:")
            for name, count in sorted(type_counts.items(), key=lambda x: -x[1]):
                lines.append(f"    {name}: {count} 次")
        return "\n".join(lines)

    def _run(self, device_id: str, hours: int = 24) -> str:
        raise NotImplementedError("Use _arun")


query_defect_stats = QueryDefectStats()