"""initial schema

Revision ID: 0001
Revises:
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=False),
        sa.Column("username", sa.String(64), nullable=False, server_default=""),
        sa.Column("gold", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("xp", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("hints_50_50", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("hints_freeze", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("hints_radar", sa.Integer(), nullable=False, server_default="3"),
    )
    op.create_table(
        "questions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("q_type", sa.Enum("CHOICE", "EXACT", name="q_type"), nullable=False),
        sa.Column("text", sa.String(500), nullable=False),
        sa.Column("correct_answer", sa.String(200), nullable=False),
        sa.Column("wrong_answers", postgresql.JSONB(), nullable=True),
        sa.Column("is_year", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.create_index("ix_questions_q_type", "questions", ["q_type"])
    op.create_table(
        "matches",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("rounds_played", sa.Integer(), nullable=False),
    )
    op.create_table(
        "match_participants",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("match_id", sa.String(32), sa.ForeignKey("matches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("is_bot", sa.Boolean(), nullable=False),
        sa.Column("place", sa.Integer(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("territories", sa.Integer(), nullable=False),
        sa.Column("gold_reward", sa.Integer(), nullable=False),
        sa.Column("xp_reward", sa.Integer(), nullable=False),
    )
    op.create_index("ix_match_participants_match_id", "match_participants", ["match_id"])
    op.create_index("ix_match_participants_user_id", "match_participants", ["user_id"])


def downgrade() -> None:
    op.drop_table("match_participants")
    op.drop_table("matches")
    op.drop_table("questions")
    op.drop_table("users")
    sa.Enum(name="q_type").drop(op.get_bind(), checkfirst=True)
