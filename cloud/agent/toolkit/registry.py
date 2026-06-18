"""工具注册表 — 收集所有可用工具。"""

from __future__ import annotations

from langchain_core.tools import BaseTool

from .base import AgentBaseTool
from .defect_detail import get_defect_detail
from .defect_history import query_defect_history
from .defect_stats import query_defect_stats
from .generate_report import generate_report
from .search_standards import search_standards

AGENT_TOOLS: list[BaseTool] = [
    query_defect_history,
    query_defect_stats,
    get_defect_detail,
    search_standards,
    generate_report,
]

__all__ = ["AGENT_TOOLS", "AgentBaseTool"]
