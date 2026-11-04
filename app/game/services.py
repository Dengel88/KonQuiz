"""Всё, что FSM берёт снаружи: вопросы, экономика (Postgres), хранилище состояния (Redis), шина событий."""

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from redis.asyncio import Redis
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.game.errors import GameError
from app.game.schemas import MatchState
from app.models import Match, MatchParticipant, QType, Question, QuestionRating, User

log = logging.getLogger(__name__)

HINT_COSTS = {"50_50": 15, "freeze": 20, "radar": 30}
HINT_COLUMNS = {"50_50": User.hints_50_50, "freeze": User.hints_freeze, "radar": User.hints_radar}

# (gold, xp) по месту: 1-е, 2-е, 3-е
PLACE_REWARDS = {1: (50, 100), 2: (15, 30), 3: (5, 10)}


class QuestionRepo:
    def __init__(self, sm: async_sessionmaker[AsyncSession]):
        self.sm = sm

    async def pick(self, q_type: QType, exclude: list[int], categories: tuple[str, ...] | None = None) -> Question:
        """Порядок: новый из темы → новый из всего банка → повтор из темы → любой повтор.

        «Новый» — не заданный в этом матче и не из группы уже заданного: вопросы одного сюжета
        подсказывают друг другу ответ (факт про Тьюринга-1950 и числовой «в каком году…»).
        """
        attempts = [(categories, exclude), (None, exclude), (categories, []), (None, [])]
        async with self.sm() as s:
            used_groups = select(Question.group_key).where(
                Question.id.in_(exclude), Question.group_key.is_not(None)).scalar_subquery()
            for cats, excl in attempts:
                stmt = select(Question).where(Question.q_type == q_type, Question.active.is_(True))
                if cats:
                    stmt = stmt.where(Question.category.in_(cats))
                if excl:
                    stmt = stmt.where(Question.id.not_in(excl))
                    stmt = stmt.where((Question.group_key.is_(None)) | Question.group_key.not_in(used_groups))
                # ORDER BY random() — ок для сотен/тысяч вопросов; на сотнях тысяч заменить
                q = (await s.execute(stmt.order_by(func.random()).limit(1))).scalar_one_or_none()
                if q:
                    return q
        raise RuntimeError(f"В базе нет вопросов типа {q_type.value} — запустите `python -m app.seed`")

    async def random_fact(self, categories: tuple[str, ...] | None = None) -> str | None:
        async with self.sm() as s:
            stmt = select(Question.fact).where(Question.fact.is_not(None), Question.active.is_(True))
            if categories:
                stmt = stmt.where(Question.category.in_(categories))
            return (await s.execute(stmt.order_by(func.random()).limit(1))).scalar_one_or_none()

    async def rate(self, user_id: int, question_id: int, value: int) -> bool:
        """Сохранить оценку (повторная перезаписывает). False — такого вопроса нет."""
        async with self.sm() as s, s.begin():
            if await s.get(Question, question_id) is None:
                return False
            row = (await s.execute(select(QuestionRating).where(
                QuestionRating.user_id == user_id, QuestionRating.question_id == question_id,
            ))).scalar_one_or_none()
            if row:
                row.value = value
            else:
                s.add(QuestionRating(user_id=user_id, question_id=question_id, value=value))
        return True

    async def count_by_category(self) -> dict[str, int]:
        async with self.sm() as s:
            rows = await s.execute(select(Question.category, func.count())
                                   .where(Question.active.is_(True)).group_by(Question.category))
            return dict(rows.all())


@dataclass
class PlayerResult:
    tg_id: int
    is_bot: bool
    place: int
    score: int
    territories: int
    gold: int
    xp: int


class Economy:
    def __init__(self, sm: async_sessionmaker[AsyncSession]):
        self.sm = sm

    async def upsert_user(self, tg_id: int, username: str) -> User:
        async with self.sm.begin() as s:
            user = await s.get(User, tg_id)
            if user is None:
                user = User(id=tg_id, username=username)
                s.add(user)
            elif username and user.username != username:
                user.username = username
        return user

    async def get_user(self, tg_id: int) -> User | None:
        async with self.sm() as s:
            return await s.get(User, tg_id)

    async def charge_hint(self, tg_id: int, hint: str) -> str:
        """Сначала тратим подсказку из запаса, если запас пуст — золото. Атомарно, без гонок."""
        col = HINT_COLUMNS[hint]
        async with self.sm.begin() as s:
            res = await s.execute(
                update(User).where(User.id == tg_id, col > 0).values({col: col - 1}).returning(User.id)
            )
            if res.first():
                return "inventory"
            cost = HINT_COSTS[hint]
            res = await s.execute(
                update(User).where(User.id == tg_id, User.gold >= cost).values(gold=User.gold - cost).returning(User.id)
            )
            if res.first():
                return "gold"
        raise GameError(f"Нет подсказки в запасе и не хватает золота ({HINT_COSTS[hint]})")

    async def save_match(self, match_id: str, rounds: int, results: list[PlayerResult]) -> None:
        async with self.sm.begin() as s:
            s.add(Match(id=match_id, rounds_played=rounds))
            await s.flush()
            for r in results:
                s.add(MatchParticipant(
                    match_id=match_id, user_id=None if r.is_bot else r.tg_id, is_bot=r.is_bot,
                    place=r.place, score=r.score, territories=r.territories,
                    gold_reward=r.gold, xp_reward=r.xp,
                ))
                if not r.is_bot:
                    await s.execute(
                        update(User).where(User.id == r.tg_id)
                        .values(gold=User.gold + r.gold, xp=User.xp + r.xp)
                    )


class MatchStore:
    """MatchState в Redis: быстрый доступ снаружи процесса и основа для будущего восстановления."""

    def __init__(self, redis: Redis, ttl: int):
        self.redis = redis
        self.ttl = ttl

    @staticmethod
    def key(match_id: str) -> str:
        return f"match:{match_id}"

    async def save(self, state: MatchState) -> None:
        await self.redis.set(self.key(state.match_id), state.model_dump_json(), ex=self.ttl)

    async def load(self, match_id: str) -> MatchState | None:
        raw = await self.redis.get(self.key(match_id))
        return MatchState.model_validate_json(raw) if raw else None


class EventBus:
    """Внутренняя шина одного матча: движок публикует, подписчики (сокеты, боты) читают свои очереди."""

    def __init__(self) -> None:
        self._subs: set[asyncio.Queue[dict[str, Any]]] = set()

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._subs.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subs.discard(q)

    def publish(self, event: dict[str, Any]) -> None:
        for q in self._subs:
            q.put_nowait(event)


@dataclass
class EngineDeps:
    settings: Settings
    questions: QuestionRepo
    economy: Economy
    store: MatchStore
