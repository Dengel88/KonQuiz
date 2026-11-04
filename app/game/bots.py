"""Боты: независимые asyncio-задачи.

Бот подписан на шину матча, на каждое обновление смотрит в MatchState и, если от
него что-то ждут, через задержку отправляет в движок ровно такой же payload, какой
прислал бы клиент по WebSocket (`engine.submit`). Никаких обходных путей в FSM.
"""

from __future__ import annotations

import asyncio
import random
from typing import TYPE_CHECKING, Any

from app.game.schemas import MatchState
from app.models import QType

if TYPE_CHECKING:
    from app.game.engine import MatchEngine


class BotBrain:
    def __init__(self, engine: MatchEngine, bot_id: int, rng: random.Random):
        self.e = engine
        self.bot_id = bot_id
        self.rng = rng
        self._handled_phase = -1
        self._pending: asyncio.Task | None = None

    async def run(self) -> None:
        q = self.e.bus.subscribe()
        try:
            self._react()
            while True:
                event = await q.get()
                if event["type"] == "end":
                    return
                if event["type"] == "state":
                    self._react()
        finally:
            self.e.bus.unsubscribe(q)
            if self._pending:
                self._pending.cancel()

    def _react(self) -> None:
        s = self.e.state
        if s.phase == self._handled_phase:
            return  # повторная рассылка в той же фазе (например, после «заморозки»)
        decision = self._decide(s)
        if decision is None:
            return
        self._handled_phase = s.phase
        (lo, hi), payload = decision
        payload["phase"] = s.phase
        if self._pending:
            self._pending.cancel()
        self._pending = asyncio.create_task(self._act(lo, hi, payload))

    async def _act(self, lo: float, hi: float, payload: dict[str, Any]) -> None:
        await asyncio.sleep(self.rng.uniform(lo, hi))  # никогда не отвечаем мгновенно
        self.e.submit(self.bot_id, payload)

    def _decide(self, s: MatchState) -> tuple[tuple[float, float], dict[str, Any]] | None:
        cfg = self.e.settings
        answer_delay = (cfg.bot_delay_min, cfg.bot_delay_max)
        pick_delay = (cfg.bot_pick_delay_min, cfg.bot_pick_delay_max)
        cq = s.current_question

        if cq and self.bot_id in s.question_participants and self.bot_id not in s.answers:
            return answer_delay, {"action": "answer", "value": self.answer(cq)}
        if s.picker_tg_id == self.bot_id and s.pick_options:
            return pick_delay, {"action": "pick", "territory": self.rng.choice(s.pick_options)}
        if s.state_name == "BATTLE_WAIT" and s.current_turn_tg_id == self.bot_id:
            attacks = self.e.valid_attacks(self.bot_id)
            if attacks:
                src, tgt = self.rng.choice(attacks)
                return pick_delay, {"action": "attack", "source_territory": src, "target_territory": tgt}
        return None

    def answer(self, cq: dict[str, Any]) -> int:
        correct = cq["correct"]
        if cq["q_type"] == QType.CHOICE.value:
            if self.rng.random() < 0.6:
                return correct
            return self.rng.choice([i for i in range(len(cq["options"])) if i != correct])
        if cq.get("is_year"):
            return int(round(correct)) + self.rng.randint(-15, 15)
        return int(correct * self.rng.uniform(0.7, 1.3))
