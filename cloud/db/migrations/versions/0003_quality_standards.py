"""quality_standards table with vector column

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-16
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "quality_standards",
        sa.Column("id", postgresql.UUID(), primary_key=True),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source", sa.String(100), nullable=True),
        sa.Column(
            "embedding",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "idx_qs_category",
        "quality_standards",
        ["category"],
    )
    op.execute(
        "ALTER TABLE quality_standards "
        "ALTER COLUMN embedding TYPE vector(1024) USING embedding::vector"
    )
    op.execute(
        "CREATE INDEX idx_qs_embedding ON quality_standards "
        "USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_qs_embedding")
    op.drop_table("quality_standards")