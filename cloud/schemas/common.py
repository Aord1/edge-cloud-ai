"""通用响应模型。"""

from __future__ import annotations

from pydantic import BaseModel


class BaseResponse(BaseModel):
    code: int = 0
    message: str = "ok"
