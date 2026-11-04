"""Состояние матча. Хранится в Redis как JSON (Pydantic).

Поля из ТЗ сохранены как есть; ниже `# --- расширения` — то, без чего FSM
не описать: номер фазы (защита от устаревших таймеров/ответов), очередь ходов,
контекст выбора территории и боя, результат последнего вопроса.
"""

import time
from typing import Any

from pydantic import BaseModel, Field


class PlayerState(BaseModel):
    tg_id: int
    is_bot: bool
    score: int = 0
    connected: bool = True
    color: str
    used_hints: list[str] = Field(default_factory=list)
    # --- расширения
    username: str = ""
    eliminated: bool = False


class MatchState(BaseModel):
    match_id: str
    state_name: str
    topic: str = "general"
    map_id: str = "russia"
    players: dict[int, PlayerState] = Field(default_factory=dict)
    territories: dict[int, int | None] = Field(default_factory=dict)
    capitals: dict[int, int] = Field(default_factory=dict)
    current_turn_tg_id: int | None = None
    timer_ends_at: float | None = None
    current_question: dict | None = None
    answers: dict[int, Any] = Field(default_factory=dict)  # tg_id -> {"value": ..., "ts": float}
    # --- расширения
    phase: int = 0  # растёт при каждом входе в состояние
    question_participants: list[int] = Field(default_factory=list)
    used_question_ids: list[int] = Field(default_factory=list)
    picker_tg_id: int | None = None
    pick_options: list[int] = Field(default_factory=list)
    battle: dict | None = None  # {"attacker", "defender", "source", "target"}
    turn_order: list[int] = Field(default_factory=list)
    turn_index: int = -1
    round: int = 0
    last_result: dict | None = None  # итог последнего вопроса/боя — для экрана REVEAL
    final: dict | None = None  # итоги матча (END_GAME)
    # --- классика Конкизтадора
    values: dict[int, int] = Field(default_factory=dict)  # territory_id -> текущая стоимость земли
    towers: dict[int, int] = Field(default_factory=dict)  # tg_id -> сколько башен осталось у замка
    rounds_total: int = 4  # раундов битвы (клиент рисует трекер)
    attack_targets: list[int] = Field(default_factory=list)  # куда можно ударить в этот ход
    pick_queue: list[int] = Field(default_factory=list)  # кто ещё выбирает землю после угадайки
    winner_tg_id: int | None = None  # победитель финальной угадайки при равенстве очков

    def active_players(self) -> list[int]:
        return [pid for pid, p in self.players.items() if not p.eliminated]

    def owned_by(self, pid: int) -> list[int]:
        return [tid for tid, owner in self.territories.items() if owner == pid]

    def neutral(self) -> list[int]:
        return [tid for tid, owner in self.territories.items() if owner is None]


def public_view(s: MatchState) -> dict:
    """То, что видят клиенты: без правильного ответа и без чужих ответов до раскрытия."""
    d = s.model_dump(mode="json", exclude={"used_question_ids"})
    if d["current_question"]:
        hidden = ("correct", "is_year", "fact")  # факт часто содержит ответ — только после раскрытия
        d["current_question"] = {k: v for k, v in d["current_question"].items() if k not in hidden}
    d["answers"] = {str(pid): True for pid in s.answers}
    d["server_time"] = time.time()
    return d
