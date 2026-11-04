import enum
from datetime import datetime

from sqlalchemy import (
    JSON, BigInteger, DateTime, Enum, ForeignKey, Integer, SmallInteger, String, Text, UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

# JSONB в Postgres, обычный JSON в SQLite (тесты)
JsonB = JSON().with_variant(JSONB(), "postgresql")


class QType(str, enum.Enum):
    CHOICE = "CHOICE"  # 1 из 4
    EXACT = "EXACT"  # числовой ответ


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)  # Telegram ID
    username: Mapped[str] = mapped_column(String(64), default="")
    gold: Mapped[int] = mapped_column(Integer, default=100, server_default="100")
    xp: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    hints_50_50: Mapped[int] = mapped_column(Integer, default=3, server_default="3")
    hints_freeze: Mapped[int] = mapped_column(Integer, default=3, server_default="3")
    hints_radar: Mapped[int] = mapped_column(Integer, default=3, server_default="3")


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # постоянный ключ из app/questions/data/*.json — по нему seed обновляет вопрос
    key: Mapped[str | None] = mapped_column(String(64), unique=True, index=True, nullable=True)
    # сюжет: в одном матче не больше одного вопроса группы (чтобы один не подсказывал другой)
    group_key: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    # убранный из банка вопрос не удаляем (на нём висят оценки) — только выключаем
    active: Mapped[bool] = mapped_column(default=True, server_default="true")
    q_type: Mapped[QType] = mapped_column(Enum(QType, name="q_type"), index=True)
    text: Mapped[str] = mapped_column(String(500), unique=True)
    correct_answer: Mapped[str] = mapped_column(String(200))  # для EXACT — число строкой
    wrong_answers: Mapped[list[str] | None] = mapped_column(JsonB, nullable=True)  # 3 шт. для CHOICE
    # Ответ — год: боты ошибаются на ±15 лет, а не на ±30% (иначе «1361 год» на вопрос про 1945)
    is_year: Mapped[bool] = mapped_column(default=False, server_default="false")
    category: Mapped[str] = mapped_column(String(40), default="Разное", server_default="Разное", index=True)
    difficulty: Mapped[int] = mapped_column(SmallInteger, default=2, server_default="2")  # 1 лёгкий .. 3 сложный
    verified: Mapped[bool] = mapped_column(default=False, server_default="false")  # проверен человеком
    # «Интересный факт»: показывается после ответа и по кнопке в лобби — чтение фактов помогает играть
    fact: Mapped[str | None] = mapped_column(Text, nullable=True)


class Match(Base):
    __tablename__ = "matches"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    rounds_played: Mapped[int] = mapped_column(Integer, default=0)

    participants: Mapped[list["MatchParticipant"]] = relationship(back_populates="match")


class MatchParticipant(Base):
    __tablename__ = "match_participants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    match_id: Mapped[str] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"), index=True)
    # NULL для ботов — их нет в таблице users
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    is_bot: Mapped[bool] = mapped_column(default=False)
    place: Mapped[int] = mapped_column(Integer)
    score: Mapped[int] = mapped_column(Integer)
    territories: Mapped[int] = mapped_column(Integer)
    gold_reward: Mapped[int] = mapped_column(Integer, default=0)
    xp_reward: Mapped[int] = mapped_column(Integer, default=0)

    match: Mapped[Match] = relationship(back_populates="participants")


class QuestionRating(Base):
    """Оценка вопроса игроком после ответа: 1 — нравится, 0 — средне, -1 — не нравится.

    Одна оценка на пару (игрок, вопрос), повторная перезаписывает. Нужна, чтобы находить
    плохие вопросы в банке (см. tools/export_questions.py).
    """

    __tablename__ = "question_ratings"
    __table_args__ = (UniqueConstraint("user_id", "question_id", name="uq_question_rating"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id", ondelete="CASCADE"), index=True)
    value: Mapped[int] = mapped_column(SmallInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
