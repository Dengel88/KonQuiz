"""MatchEngine — один матч = один актор.

Все входящие события (действия игроков и ботов, таймауты, подключения) попадают
в одну очередь `inbox` и обрабатываются строго по одному. Поэтому гонки вида
«таймер истёк в тот же момент, когда пришёл последний ответ» невозможны без
всяких блокировок. Таймер несёт токен: если таймер перезапустили (заморозка)
или состояние сменилось, старый таймаут просто игнорируется.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
import uuid
from collections.abc import Callable
from dataclasses import asdict
from typing import Any

from app.game.errors import GameError
from app.game.map_topology import resolve as resolve_map
from app.game.schemas import MatchState, PlayerState, public_view
from app.game.services import HINT_COSTS, PLACE_REWARDS, EngineDeps, EventBus, PlayerResult
from app.game import states as st
from app.game.topics import resolve as resolve_topic
from app.models import QType

log = logging.getLogger(__name__)

COLORS = ["red", "blue", "green", "yellow", "purple"]
BOT_NAMES = ["Генерал Буря", "Барон Жук", "Леди Мгла", "Капитан Сыч", "Маршал Вьюга", "Графиня Искра"]


class MatchEngine:
    def __init__(
        self,
        deps: EngineDeps,
        match_id: str | None = None,
        rng: random.Random | None = None,
        on_finished: Callable[[MatchEngine], None] | None = None,
        topic: str | None = None,
        map_id: str | None = None,
    ):
        self.deps = deps
        self.settings = deps.settings
        self.rng = rng or random.Random()
        self.topic = resolve_topic(topic)
        self.map = resolve_map(map_id)
        self.state = MatchState(
            match_id=match_id or uuid.uuid4().hex[:12],
            state_name="INIT",
            topic=self.topic.id,
            map_id=self.map.id,
            territories={tid: None for tid in self.map.territories},
        )
        self.bus = EventBus()
        self.inbox: asyncio.Queue[tuple] = asyncio.Queue()
        self.current: st.GameState | None = None
        self.finished = asyncio.Event()
        self._on_finished = on_finished
        self._timer: asyncio.Task | None = None
        self._timer_token = 0
        self._loop_task: asyncio.Task | None = None
        self._bot_tasks: dict[int, asyncio.Task] = {}
        self._next_bot_id = -1

    @property
    def match_id(self) -> str:
        return self.state.match_id

    # ------------------------------------------------------------ публичный API (вызывается снаружи)

    def start(self) -> None:
        self._loop_task = asyncio.create_task(self._run(), name=f"match-{self.match_id}")

    def submit(self, pid: int, payload: dict[str, Any]) -> None:
        """Намерение игрока/бота. Время фиксируем в момент получения — по нему решаются ничьи."""
        self.inbox.put_nowait(("action", pid, payload, time.time()))

    async def request_join(self, pid: int, username: str) -> bool:
        if self.finished.is_set():
            return False
        fut: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
        self.inbox.put_nowait(("join", pid, username, fut))
        return await fut

    def request_fill_bots(self) -> None:
        self.inbox.put_nowait(("fill_bots",))

    def set_presence(self, pid: int, connected: bool) -> None:
        self.inbox.put_nowait(("presence", pid, connected))

    async def stop(self) -> None:
        self._cancel_timer()
        for t in self._bot_tasks.values():
            t.cancel()
        if self._loop_task and not self._loop_task.done():
            self._loop_task.cancel()
        self.finished.set()

    # ------------------------------------------------------------ цикл

    async def _run(self) -> None:
        await self._enter(st.MatchmakingState(self))
        await self._flush()
        while not self.finished.is_set():
            await self.process(await self.inbox.get())

    async def process(self, msg: tuple) -> None:
        kind = msg[0]
        try:
            if kind == "action":
                _, pid, payload, ts = msg
                try:
                    await self._handle_action(pid, payload, ts)
                except GameError as err:
                    self.private(pid, {"type": "error", "message": str(err)})
                    return  # состояние не менялось — рассылать нечего
            elif kind == "timeout":
                if msg[1] != self._timer_token:
                    return
                self._timer = None
                await self.current.on_timeout()
            elif kind == "join":
                _, pid, username, fut = msg
                ok = self._join(pid, username)
                if not fut.done():
                    fut.set_result(ok)
            elif kind == "fill_bots":
                if isinstance(self.current, st.MatchmakingState):
                    self.fill_with_bots()
            elif kind == "presence":
                _, pid, connected = msg
                if pid in self.state.players:
                    self.state.players[pid].connected = connected
            await self._advance()
        except Exception:
            log.exception("match %s: ошибка обработки %s", self.match_id, kind)
        await self._flush()
        if isinstance(self.current, st.EndGameState) and not self.finished.is_set():
            await self._shutdown()

    async def _handle_action(self, pid: int, payload: Any, ts: float) -> None:
        if pid not in self.state.players:
            raise GameError("Вы не участник этого матча")
        if not isinstance(payload, dict):
            raise GameError("Некорректное сообщение")
        phase = payload.get("phase")
        if phase is not None and phase != self.state.phase:
            raise GameError("Действие устарело — фаза уже сменилась")
        if "use_hint" in payload:
            await self._use_hint(pid, str(payload["use_hint"]))
            return
        await self.current.on_action(pid, payload, ts)

    async def _advance(self) -> None:
        for _ in range(64):  # предохранитель от бесконечной цепочки переходов
            nxt = await self.current.check_transitions()
            if nxt is None:
                return
            await self._enter(nxt)
        log.error("match %s: слишком длинная цепочка переходов", self.match_id)

    async def _enter(self, new: st.GameState) -> None:
        self._cancel_timer()
        s = self.state
        s.phase += 1
        s.state_name = new.name
        s.answers = {}
        s.timer_ends_at = None
        s.current_question = None
        s.question_participants = []
        s.picker_tg_id = None
        s.pick_options = []
        self.current = new
        await new.on_enter()

    async def _flush(self) -> None:
        try:
            await self.deps.store.save(self.state)
        except Exception:
            log.exception("match %s: не удалось сохранить в Redis", self.match_id)
        self.bus.publish({"type": "state", "state": public_view(self.state)})

    async def _shutdown(self) -> None:
        self._cancel_timer()
        self.bus.publish({"type": "end", "final": self.state.final})
        for t in self._bot_tasks.values():
            t.cancel()
        self.finished.set()
        if self._on_finished:
            self._on_finished(self)

    # ------------------------------------------------------------ таймеры

    def set_timer(self, seconds: float) -> None:
        self._cancel_timer()
        self.state.timer_ends_at = time.time() + seconds
        self._start_timer_task()

    def extend_timer(self, seconds: float) -> None:
        if self.state.timer_ends_at is None:
            return
        self._cancel_timer()
        self.state.timer_ends_at += seconds
        self._start_timer_task()

    def _start_timer_task(self) -> None:
        token = self._timer_token
        ends = self.state.timer_ends_at

        async def fire() -> None:
            await asyncio.sleep(max(0.0, ends - time.time()))
            self.inbox.put_nowait(("timeout", token))

        self._timer = asyncio.create_task(fire())

    def _cancel_timer(self) -> None:
        self._timer_token += 1  # даже уже поставленный в очередь таймаут станет недействительным
        if self._timer:
            self._timer.cancel()
            self._timer = None

    # ------------------------------------------------------------ игроки и боты

    def _join(self, pid: int, username: str) -> bool:
        if pid in self.state.players:
            return True  # переподключение
        if not isinstance(self.current, st.MatchmakingState):
            return False
        if len(self.state.players) >= self.settings.players_per_match:
            return False
        self._add_player(pid, username, is_bot=False)
        return True

    def _add_player(self, pid: int, username: str, is_bot: bool) -> None:
        color = COLORS[len(self.state.players) % len(COLORS)]
        self.state.players[pid] = PlayerState(tg_id=pid, is_bot=is_bot, color=color, username=username)

    def fill_with_bots(self) -> None:
        from app.game.bots import BotBrain  # ленивый импорт: bots импортирует engine

        taken = {p.username for p in self.state.players.values()}
        names = [n for n in BOT_NAMES if n not in taken]
        while len(self.state.players) < self.settings.players_per_match:
            bid = self._next_bot_id
            self._next_bot_id -= 1
            self._add_player(bid, names.pop(0), is_bot=True)
            brain = BotBrain(self, bid, random.Random(self.rng.random()))
            self._bot_tasks[bid] = asyncio.create_task(brain.run(), name=f"bot{bid}-{self.match_id}")

    def private(self, pid: int, data: dict[str, Any]) -> None:
        self.bus.publish({"type": "private", "to": pid, "data": data})

    # ------------------------------------------------------------ вопросы

    async def ask_question(self, q_type: QType, participants: list[int], duration: float) -> None:
        s = self.state
        q = await self.deps.questions.pick(q_type, s.used_question_ids, self.topic.categories)
        s.used_question_ids.append(q.id)
        cq: dict[str, Any] = {
            "id": q.id, "q_type": q.q_type.value, "text": q.text, "is_year": q.is_year,
            "category": q.category, "fact": q.fact,
        }
        if q_type is QType.CHOICE:
            options = [q.correct_answer, *q.wrong_answers]
            self.rng.shuffle(options)
            cq["options"] = options
            cq["correct"] = options.index(q.correct_answer)
        else:
            value = float(q.correct_answer)
            cq["correct"] = int(value) if value.is_integer() else value
        s.current_question = cq
        s.question_participants = list(participants)
        self.set_timer(duration)

    def rank_exact(self) -> list[int]:
        """Ответившие по близости к правильному; при равной близости раньше — выше."""
        s = self.state
        correct = s.current_question["correct"]
        rows = [
            (abs(a["value"] - correct), a["ts"], pid)
            for pid, a in s.answers.items()
            if pid in s.question_participants
        ]
        rows.sort()
        return [pid for *_, pid in rows]

    def question_result(self, kind: str, **extra: Any) -> dict[str, Any]:
        s = self.state
        cq = s.current_question
        result = {
            "kind": kind,
            "question_id": cq["id"],  # для оценки 👍/😐/👎 после ответа
            "text": cq["text"],
            "q_type": cq["q_type"],
            "options": cq.get("options"),
            "correct": cq["correct"],
            "fact": cq.get("fact"),
            "answers": {str(pid): a["value"] for pid, a in s.answers.items()},
            **extra,
        }
        s.last_result = result
        return result

    # ------------------------------------------------------------ бой и ходы

    def valid_attacks(self, pid: int) -> list[tuple[int, int]]:
        t = self.state.territories
        return [
            (src, tgt)
            for src in self.state.owned_by(pid)
            for tgt in self.map.neighbors(src)
            if t[tgt] not in (None, pid)
        ]

    def start_battles(self) -> st.GameState:
        s = self.state
        s.turn_order = s.active_players()
        self.rng.shuffle(s.turn_order)
        s.round = 1
        s.turn_index = -1
        return self.next_turn()

    def next_turn(self) -> st.GameState:
        s = self.state
        if len(s.active_players()) <= 1:
            return st.EndGameState(self)
        for _ in range(len(s.turn_order) * (self.settings.battle_rounds + 1)):
            s.turn_index += 1
            if s.turn_index >= len(s.turn_order):
                s.turn_index = 0
                s.round += 1
            if s.round > self.settings.battle_rounds:
                s.round = self.settings.battle_rounds
                break
            pid = s.turn_order[s.turn_index]
            if not s.players[pid].eliminated:
                s.current_turn_tg_id = pid
                return st.BattleWaitState(self, pid)
        return st.EndGameState(self)

    def finish_battle(self, captured: bool) -> None:
        s = self.state
        b = s.battle
        if captured:
            s.territories[b["target"]] = b["attacker"]
            if s.capitals.get(b["defender"]) == b["target"]:
                del s.capitals[b["defender"]]
            if not s.owned_by(b["defender"]):
                s.players[b["defender"]].eliminated = True
        if s.last_result is not None:
            s.last_result["battle"] = dict(b)
            s.last_result["outcome"] = "captured" if captured else "defended"
        s.battle = None

    # ------------------------------------------------------------ подсказки

    async def _use_hint(self, pid: int, hint: str) -> None:
        s = self.state
        if hint not in HINT_COSTS:
            raise GameError("Неизвестная подсказка")
        cq = s.current_question
        if not isinstance(self.current, st.QuestionState) or cq is None:
            raise GameError("Подсказки доступны только во время вопроса")
        if pid not in s.question_participants:
            raise GameError("Вы не участвуете в этом вопросе")
        if pid in s.answers:
            raise GameError("Вы уже ответили")
        player = s.players[pid]
        if player.is_bot:
            raise GameError("Боты не пользуются подсказками")
        if hint in player.used_hints:
            raise GameError("Эта подсказка уже использована в матче")
        if hint in ("50_50", "radar") and cq["q_type"] != QType.CHOICE.value:
            raise GameError("Эта подсказка работает только для вопросов с вариантами")

        paid_with = await self.deps.economy.charge_hint(pid, hint)
        player.used_hints.append(hint)
        data: dict[str, Any] = {"type": "hint", "hint": hint, "paid_with": paid_with}

        if hint == "50_50":
            wrong = [i for i in range(len(cq["options"])) if i != cq["correct"]]
            data["remove"] = sorted(self.rng.sample(wrong, 2))
        elif hint == "freeze":
            self.extend_timer(self.settings.freeze_bonus)  # новое timer_ends_at уйдёт всем в рассылке
        elif hint == "radar":
            data["distribution"] = self._radar(cq["correct"], len(cq["options"]))
        self.private(pid, data)

    def _radar(self, correct: int, n: int) -> list[int]:
        """«Помощь зала»: правильный ~65% (±5), остаток случайно раскидан по неправильным."""
        c = max(50, min(80, round(self.rng.gauss(65, 5))))
        rest = 100 - c
        weights = [self.rng.random() + 0.1 for _ in range(n - 1)]
        parts = [int(rest * w / sum(weights)) for w in weights]
        parts[0] += rest - sum(parts)
        it = iter(parts)
        return [c if i == correct else next(it) for i in range(n)]

    # ------------------------------------------------------------ финал

    async def finish_match(self) -> None:
        s = self.state
        s.current_turn_tg_id = None
        owned = {pid: s.owned_by(pid) for pid in s.players}
        for pid, p in s.players.items():
            p.score = sum(self.map.territories[t].base_points for t in owned[pid])
            if pid in s.capitals:
                p.score += self.settings.capital_bonus

        ranked = sorted(s.players.values(), key=lambda p: (-p.score, -len(owned[p.tg_id]), self.rng.random()))
        results = []
        for place, p in enumerate(ranked, start=1):
            gold, xp = (0, 0) if p.is_bot else PLACE_REWARDS.get(place, (0, 0))
            results.append(PlayerResult(
                tg_id=p.tg_id, is_bot=p.is_bot, place=place, score=p.score,
                territories=len(owned[p.tg_id]), gold=gold, xp=xp,
            ))
        try:
            await self.deps.economy.save_match(s.match_id, s.round, results)
        except Exception:
            log.exception("match %s: не удалось сохранить итоги", s.match_id)
        s.final = {"results": [asdict(r) for r in results]}
