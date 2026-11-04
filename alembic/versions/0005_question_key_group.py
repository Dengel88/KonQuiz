"""question key, group, active

Revision ID: 0005
Revises: 0004
"""
import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # key заполнит seed: у старых строк он пустой, seed найдёт их по тексту и проставит ключ
    op.add_column("questions", sa.Column("key", sa.String(64), nullable=True))
    op.create_index("ix_questions_key", "questions", ["key"], unique=True)
    op.add_column("questions", sa.Column("group_key", sa.String(64), nullable=True))
    op.create_index("ix_questions_group_key", "questions", ["group_key"])
    op.add_column("questions", sa.Column("active", sa.Boolean(), server_default="true", nullable=False))


def downgrade() -> None:
    op.drop_column("questions", "active")
    op.drop_index("ix_questions_group_key", table_name="questions")
    op.drop_column("questions", "group_key")
    op.drop_index("ix_questions_key", table_name="questions")
    op.drop_column("questions", "key")
