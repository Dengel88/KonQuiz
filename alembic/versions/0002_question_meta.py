"""question category / difficulty / verified

Revision ID: 0002
Revises: 0001
"""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("questions", sa.Column("category", sa.String(40), nullable=False, server_default="Разное"))
    op.add_column("questions", sa.Column("difficulty", sa.SmallInteger(), nullable=False, server_default="2"))
    op.add_column("questions", sa.Column("verified", sa.Boolean(), nullable=False, server_default="false"))
    op.create_index("ix_questions_category", "questions", ["category"])
    op.create_unique_constraint("uq_questions_text", "questions", ["text"])


def downgrade() -> None:
    op.drop_constraint("uq_questions_text", "questions")
    op.drop_index("ix_questions_category", "questions")
    op.drop_column("questions", "verified")
    op.drop_column("questions", "difficulty")
    op.drop_column("questions", "category")
