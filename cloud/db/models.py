"""ORM 数据模型。"""

from __future__ import annotations

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from ..config import settings


class Base(DeclarativeBase):
    pass


class DetectionLog(Base):
    __tablename__ = "detection_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    device_id: Mapped[str] = mapped_column(String(64), index=True)
    reason: Mapped[str] = mapped_column(String(64))
    decision: Mapped[str] = mapped_column(String(16), default="CLOUD")
    detections: Mapped[dict] = mapped_column(JSONB)
    image_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    avg_confidence: Mapped[float] = mapped_column(Float)
    inference_ms: Mapped[float] = mapped_column(Float)
    agent_review: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    review: Mapped["DefectReview | None"] = relationship(
        "DefectReview", back_populates="defect_log", uselist=False
    )


class DefectReview(Base):
    __tablename__ = "defect_reviews"

    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    defect_log_id: Mapped[uuid.UUID] = mapped_column(
        UUID, ForeignKey("detection_logs.id", ondelete="CASCADE"), unique=True, index=True
    )
    verdict: Mapped[str] = mapped_column(String(32), default="")
    reasoning_chain: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    tool_calls: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    reviewed_by: Mapped[str] = mapped_column(String(64), default="")
    reviewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    defect_log: Mapped["DetectionLog"] = relationship(
        "DetectionLog", back_populates="review"
    )


class QualityStandard(Base):
    __tablename__ = "quality_standards"

    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    category: Mapped[str] = mapped_column(String(50), index=True)
    title: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text)
    source: Mapped[str | None] = mapped_column(String(100), nullable=True)
    embedding = mapped_column(Vector(settings.embedding_dim), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
