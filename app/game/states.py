"""Состояния FSM (паттерн State).

Контракт: движок вызывает on_enter() при входе, on_action()/on_timeout() на события,
а после каждого события — check_transitions(); если он вернул новое состояние, движок
в него переходит. Состояния сами ничего не шлют клиентам — движок рассылает
снимок MatchState после обработки каждого события.
"""

from __future__ import annotations

import math
from abc import abstractmethod
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, ClassVar

from app.game.errors import GameError
from app.game.schemas import MatchState
from app.models import QType

if TYPE_CHECKING:
    from app.game.engine import MatchEngine


class GameState:
    name: ClassVar[str]

    def __init__(self, engine: MatchEngine):
        self.e = engine

    @property
    def s(self) -> MatchState:
        return self.e.state

    async def on_enter(self) -> None:
        pass

    async def on_action(self, pid: int, payload: dict[str, Any], ts: float) -> None:
        raise GameError("Сейчас это действие недоступно")

    async def on_timeout(self) -> None:
        pass

    async def check_transitions(self) -> GameState | None:
        return None


# ---------------------------------------------------------------- matchmaking

class MatchmakingState(GameState):
    name = "MATCHMAKING"

    async def on_enter(self) -> None:
        self.e.set_timer(self.e.settings.matchmaking_timeout)

    async def on_timeout(self) -> None:
        self.e.fill_with_bots()

    async def check_transitions(self) -> GameState | None:
        if len(self.s.players) >= self.e.settings.players_per_match:
            return CapitalRevealState(self.e, self.e.assign_capitals())
        return None


# ---------------------------------------------------------------- вопросы

class QuestionState(GameState):
    q_type: ClassVar[QType]

    def __init__(self, engine: MatchEngine, participants: list[int]):
        super().__init__(engine)
        self.participants = participants
        self.timed_out = False

    def duration(self) -> float:
        st = self.e.settings
        return st.exact_question_time if self.q_type is QType.EXACT else st.choice_question_time

    async def on_enter(self) -> None:
        await self.e.ask_question(self.q_type, self.participants, self.duration())

    async def on_action(self, pid: int, payload: dict[str, Any], ts: float) -> None:
        if payload.get("action") != "answer":
            raise GameError("Ожидается ответ на вопрос")
        if pid not in self.participants:
            raise GameError("Вы не участвуете в этом вопросе")
        if pid in self.s.answers:
            raise GameError("Ответ уже принят")
        self.s.answers[pid] = {"value": self._parse(payload.get("value")), "ts": ts}

    def _parse(self, raw: Any) -> int | float:
        if isinstance(raw, bool):
            raise GameError("Некорректный ответ")
        if self.q_type is QType.CHOICE:
            n = len(self.s.current_question["options"])
            if not isinstance(raw, int) or not 0 <= raw < n:
                raise GameError(f"Ответ — номер варианта 0..{n - 1}")
            return raw
        try:
            value = float(raw)
        except (TypeError, ValueError):
            raise GameError("Ответ должен быть числом") from None
        if not math.isfinite(value):
            raise GameError("Ответ должен быть числом")
        return int(value) if value.is_integer() else value

    async def on_timeout(self) -> None:
        self.timed_out = True

    def _everyone_answered(self) -> bool:
        # отключившихся не ждём — иначе каждый вопрос тянулся бы до таймаута
        return all(
            pid in self.s.answers or not self.s.players[pid].connected for pid in self.participants
        )

    async def check_transitions(self) -> GameState | None:
        if self.timed_out or self._everyone_answered():
            return await self.resolve()
        return None

    @abstractmethod
    async def resolve(self) -> GameState: ...


class ExpansionQuestionState(QuestionState):
    name = "EXPANSION"
    q_type = QType.EXACT

    async def resolve(self) -> GameState:
        # 1-е место берёт 2 земли, 2-е — одну, 3-е ничего (при равной точности — кто быстрее)
        ranking = self.e.full_ranking(self.participants)
        queue = [pid for pid, n in zip(ranking, self.e.settings.expansion_picks) for _ in range(n)]
        self.e.question_result("expansion_question", winner=ranking[0], ranking=self.e.rank_exact(),
                               picks={str(pid): queue.count(pid) for pid in dict.fromkeys(queue)})
        return RevealState(self.e, lambda: ExpansionPickState(self.e, queue))


class BattleQuestionState(QuestionState):
    name = "BATTLE_QUESTION"
    q_type = QType.CHOICE

    def __init__(self, engine: MatchEngine):
        b = engine.state.battle
        super().__init__(engine, [b["attacker"], b["defender"]])

    async def resolve(self) -> GameState:
        b = self.s.battle
        correct = self.s.current_question["correct"]

        def right(pid: int) -> bool:
            return self.s.answers.get(pid, {}).get("value") == correct

        a_ok, d_ok = right(b["attacker"]), right(b["defender"])
        if a_ok and d_ok:
            self.e.question_result("battle_question", outcome="tiebreaker")
            return RevealState(self.e, lambda: BattleTiebreakerState(self.e))
        self.e.question_result("battle_question")
        nxt = self.e.finish_battle(captured=a_ok and not d_ok, defense_bonus=d_ok and not a_ok)
        return RevealState(self.e, nxt)


class BattleTiebreakerState(QuestionState):
    name = "BATTLE_TIEBREAKER"
    q_type = QType.EXACT

    def __init__(self, engine: MatchEngine):
        b = engine.state.battle
        super().__init__(engine, [b["attacker"], b["defender"]])

    async def resolve(self) -> GameState:
        ranking = self.e.rank_exact()
        b = self.s.battle
        winner = ranking[0] if ranking else b["defender"]  # никто не ответил — защитник удержал
        self.e.question_result("battle_tiebreaker", winner=winner, ranking=ranking)
        nxt = self.e.finish_battle(captured=winner == b["attacker"])
        return RevealState(self.e, nxt)


class FinalTiebreakerState(QuestionState):
    """Очков поровну на первом месте — угадайка решает, кто победил. Ничьей не бывает."""

    name = "FINAL_TIEBREAKER"
    q_type = QType.EXACT

    async def resolve(self) -> GameState:
        ranking = self.e.full_ranking(self.participants)
        self.s.winner_tg_id = ranking[0]
        self.e.question_result("final_tiebreaker", winner=ranking[0], ranking=self.e.rank_exact())
        return RevealState(self.e, lambda: EndGameState(self.e))


# ---------------------------------------------------------------- выбор территории

class PickState(GameState):
    def __init__(self, engine: MatchEngine, picker: int):
        super().__init__(engine)
        self.picker = picker
        self.chosen: int | None = None

    @abstractmethod
    def options(self) -> list[int]: ...

    @abstractmethod
    def apply(self, tid: int) -> None: ...

    @abstractmethod
    def next_state(self) -> GameState: ...

    async def on_enter(self) -> None:
        self.s.picker_tg_id = self.picker
        self.s.pick_options = self.options()
        self.e.set_timer(self.e.settings.pick_time)

    async def on_action(self, pid: int, payload: dict[str, Any], ts: float) -> None:
        if payload.get("action") != "pick":
            raise GameError("Ожидается выбор территории")
        if pid != self.picker:
            raise GameError("Сейчас выбирает другой игрок")
        tid = payload.get("territory")
        if tid not in self.s.pick_options:
            raise GameError("Эту территорию выбрать нельзя")
        self.chosen = tid

    async def on_timeout(self) -> None:
        self.chosen = self.e.rng.choice(self.s.pick_options)  # AFK — выбираем за игрока

    async def check_transitions(self) -> GameState | None:
        if self.chosen is None:
            return None
        self.apply(self.chosen)
        return self.next_state()


class ExpansionPickState(PickState):
    name = "EXPANSION_PICK"

    def __init__(self, engine: MatchEngine, queue: list[int]):
        super().__init__(engine, queue[0])
        self.queue = queue

    async def on_enter(self) -> None:
        self.s.pick_queue = self.queue[1:]
        await super().on_enter()

    def options(self) -> list[int]:
        free = set(self.s.neutral())
        adjacent = {n for t in self.s.owned_by(self.picker) for n in self.e.map.neighbors(t) if n in free}
        return sorted(adjacent or free)

    def apply(self, tid: int) -> None:
        self.e.take_land(self.picker, tid)

    def next_state(self) -> GameState:
        self.s.pick_queue = []
        if not self.s.neutral():
            return self.e.start_battles()
        if len(self.queue) > 1:
            return ExpansionPickState(self.e, self.queue[1:])
        return ExpansionQuestionState(self.e, self.s.active_players())


# ---------------------------------------------------------------- бой

class BattleWaitState(GameState):
    """Ход атакующего: тап по вражеской земле. Откуда бить — сервер выберет сам (клиент может подсказать)."""

    name = "BATTLE_WAIT"

    def __init__(self, engine: MatchEngine, attacker: int):
        super().__init__(engine)
        self.attacker = attacker
        self.targets: list[int] = []
        self.chosen: tuple[int, int] | None = None

    async def on_enter(self) -> None:
        self.targets = self.e.attack_targets(self.attacker)
        self.s.attack_targets = list(self.targets)
        if self.targets:
            self.e.set_timer(self.e.settings.attack_choice_time)

    async def on_action(self, pid: int, payload: dict[str, Any], ts: float) -> None:
        if pid != self.attacker:
            raise GameError("Сейчас ход другого игрока")
        if payload.get("action", "attack") != "attack":
            raise GameError("Ожидается выбор атаки")
        tgt = payload.get("target_territory")
        t = self.s.territories
        if tgt not in t or t[tgt] in (None, pid):
            raise GameError("Цель должна принадлежать противнику")
        if tgt not in self.targets:
            if self.s.round <= 1 and self.e.is_castle(tgt):
                raise GameError("В первом раунде замки атаковать нельзя")
            raise GameError("Цель не граничит с вашими землями")
        src = payload.get("source_territory")
        if src is None or t.get(src) != pid or tgt not in self.e.map.neighbors(src):
            src = self.e.pick_source(pid, tgt)
        self.chosen = (src, tgt)

    async def on_timeout(self) -> None:
        tgt = self.e.rng.choice(self.targets)
        self.chosen = (self.e.pick_source(self.attacker, tgt), tgt)

    async def check_transitions(self) -> GameState | None:
        if not self.targets:
            self.s.last_result = {"kind": "turn_skipped", "player": self.attacker}
            return self.e.next_turn()
        if self.chosen is None:
            return None
        src, tgt = self.chosen
        self.s.battle = {
            "attacker": self.attacker, "defender": self.s.territories[tgt], "source": src, "target": tgt,
        }
        return BattleQuestionState(self.e)


# ---------------------------------------------------------------- служебные

class RevealState(GameState):
    """Пауза после вопроса: клиент показывает правильный ответ и анимацию, таймер идёт на сервере."""

    name = "REVEAL"

    def __init__(self, engine: MatchEngine, next_factory: Callable[[], GameState]):
        super().__init__(engine)
        self.next_factory = next_factory
        self.done = False

    async def on_enter(self) -> None:
        if self.e.settings.reveal_time <= 0:
            self.done = True
        else:
            self.e.set_timer(self.e.settings.reveal_time)

    async def on_timeout(self) -> None:
        self.done = True

    async def check_transitions(self) -> GameState | None:
        return self.next_factory() if self.done else None


class CapitalRevealState(GameState):
    """Замки раздаются по одному: каждый — со своим роликом «держава основана»."""

    name = "REALM_REVEAL"

    def __init__(self, engine: MatchEngine, queue: list[tuple[int, int]]):
        super().__init__(engine)
        self.queue = queue
        self.done = False

    async def on_enter(self) -> None:
        pid, tid = self.queue[0]
        self.e.place_capital(pid, tid)
        self.s.last_result = {"kind": "capital_assigned", "player": pid, "territory": tid}
        if self.e.settings.realm_reveal_time <= 0:
            self.done = True
        else:
            self.e.set_timer(self.e.settings.realm_reveal_time)

    async def on_timeout(self) -> None:
        self.done = True

    async def check_transitions(self) -> GameState | None:
        if not self.done:
            return None
        if len(self.queue) > 1:
            return CapitalRevealState(self.e, self.queue[1:])
        return ExpansionQuestionState(self.e, self.s.active_players())


class EndGameState(GameState):
    name = "END_GAME"

    async def on_enter(self) -> None:
        await self.e.finish_match()
