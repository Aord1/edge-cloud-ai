"""initial schema — detection_logs + defect_reviews

Revision ID: 0001
Revises:
Create Date: 2026-06-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "detection_logs",
        sa.Column("id", postgresql.UUID(), primary_key=True),
        sa.Column("device_id", sa.String(64), index=True, nullable=False),
        sa.Column("reason", sa.String(64), nullable=False),
        sa.Column("decision", sa.String(16), server_default="CLOUD", nullable=False),
        sa.Column("detections", postgresql.JSONB(), nullable=False),
        sa.Column("image_path", sa.String(512), nullable=True),
        sa.Column("avg_confidence", sa.Float(), nullable=False),
        sa.Column("inference_ms", sa.Float(), nullable=False),
        sa.Column("agent_review", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_table(
        "defect_reviews",
        sa.Column("id", postgresql.UUID(), primary_key=True),
        sa.Column(
            "defect_log_id",
            postgresql.UUID(),
            sa.ForeignKey("detection_logs.id", ondelete="CASCADE"),
            unique=True,
            index=True,
            nullable=False,
        ),
        sa.Column("verdict", sa.String(32), server_default="", nullable=False),
        sa.Column("reasoning_chain", postgresql.JSONB(), nullable=True),
        sa.Column("tool_calls", postgresql.JSONB(), nullable=True),
        sa.Column("reviewed_by", sa.String(64), server_default="", nullable=False),
        sa.Column(
            "reviewed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("defect_reviews")
    op.drop_table("detection_logs")
