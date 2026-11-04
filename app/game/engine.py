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
            rounds_total=self.settings.battle_rounds,
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
        s.attack_targets = []
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
            "is_year": cq.get("is_year", False),  # годы показываем без разделителя: «1896», не «1 896»
            "answers": {str(pid): a["value"] for pid, a in s.answers.items()},
            **extra,
        }
        s.last_result = result
        return result

    # ------------------------------------------------------------ бой и ходы

    # ---- замки (классика: случайно, не вплотную, 1000 очков и 3 башни)

    def assign_capitals(self) -> list[tuple[int, int]]:
        """Случайные столицы, не граничащие друг с другом (если карта позволяет)."""
        players = self.state.active_players()
        tids = list(self.map.territories)
        for _ in range(500):
            picked = self.rng.sample(tids, len(players))
            if all(b not in self.map.neighbors(a) for a in picked for b in picked if a != b):
                break
        return list(zip(players, picked))

    def place_capital(self, pid: int, tid: int) -> None:
        s, cfg = self.state, self.settings
        s.territories[tid] = pid
        s.capitals[pid] = tid
        s.values[tid] = cfg.capital_value
        s.towers[pid] = cfg.capital_towers
        s.players[pid].score += cfg.capital_value

    def take_land(self, pid: int, tid: int) -> None:
        """Экспансия: свободная земля стоит base_points (200)."""
        s = self.state
        value = self.map.territories[tid].base_points
        s.territories[tid] = pid
        s.values[tid] = value
        s.players[pid].score += value

    def full_ranking(self, participants: list[int]) -> list[int]:
        """Ответившие по точности, за ними — молчавшие в случайном порядке."""
        ranked = self.rank_exact()
        rest = [p for p in participants if p not in ranked]
        self.rng.shuffle(rest)
        return ranked + rest

    # ---- бой и ходы

    def is_castle(self, tid: int) -> bool:
        return tid in self.state.capitals.values()

    def attack_targets(self, pid: int) -> list[int]:
        """Раунд 1 — только соседние земли без замков; средние — соседние вместе с замками;
        последний — любая вражеская земля. Если по правилу раунда бить некуда — ослабляем правило,
        чтобы ход не сгорел впустую."""
        s = self.state
        enemy = {t for t, o in s.territories.items() if o is not None and o != pid}
        near = {n for t in s.owned_by(pid) for n in self.map.neighbors(t)} & enemy
        if s.round >= s.rounds_total:
            return sorted(enemy)
        if s.round <= 1:
            no_castles = {t for t in near if not self.is_castle(t)}
            if no_castles:
                return sorted(no_castles)
        return sorted(near or enemy)

    def valid_attacks(self, pid: int) -> list[tuple[int, int]]:
        return [(self.pick_source(pid, t), t) for t in self.attack_targets(pid)]

    def pick_source(self, pid: int, tgt: int) -> int:
        """Откуда «летит» стрела: соседняя своя земля (лучше не замок), иначе — замок/любая своя."""
        s = self.state
        own = s.owned_by(pid)
        near = [t for t in own if tgt in self.map.neighbors(t)]
        if near:
            return min(near, key=lambda t: (self.is_castle(t), t))
        cap = s.capitals.get(pid)
        return cap if cap is not None else own[0]

    def start_battles(self) -> st.GameState:
        s = self.state
        s.rounds_total = self.settings.battle_rounds
        s.round = 0
        s.turn_index = len(s.turn_order)  # next_turn сразу откроет раунд 1
        s.turn_order = []
        return self.next_turn()

    def _open_round(self) -> None:
        """Раунды 1..N-1 — случайный порядок, последний — по очкам: лидер бьёт первым."""
        s = self.state
        s.round += 1
        s.turn_index = 0
        order = s.active_players()
        if s.round >= s.rounds_total:
            order.sort(key=lambda p: (-s.players[p].score, self.rng.random()))
        else:
            self.rng.shuffle(order)
        s.turn_order = order

    def next_turn(self) -> st.GameState:
        s = self.state
        if len(s.active_players()) <= 1:
            return self.end_game()
        while True:
            s.turn_index += 1
            if s.turn_index >= len(s.turn_order):
                if s.round >= s.rounds_total:
                    return self.end_game()
                self._open_round()
            pid = s.turn_order[s.turn_index]
            if not s.players[pid].eliminated:
                s.current_turn_tg_id = pid
                return st.BattleWaitState(self, pid)

    def end_game(self) -> st.GameState:
        """Ничьей не бывает: равенство на первом месте решает угадайка."""
        s = self.state
        s.current_turn_tg_id = None
        alive = [p for p in s.players.values() if not p.eliminated]
        top = max(p.score for p in alive)
        tied = [p.tg_id for p in alive if p.score == top]
        if len(tied) > 1:
            return st.FinalTiebreakerState(self, tied)
        return st.EndGameState(self)

    def finish_battle(self, captured: bool, defense_bonus: bool = False) -> Callable[[], st.GameState]:
        """Применить итог боя. Возвращает, что будет после паузы: следующий ход или продолжение осады."""
        s, cfg = self.state, self.settings
        b = s.battle
        atk, dfd, tgt = b["attacker"], b["defender"], b["target"]
        A, D = s.players[atk], s.players[dfd]
        res = s.last_result if s.last_result is not None else {}
        res["battle"] = dict(b)

        if captured and s.capitals.get(dfd) == tgt:
            s.towers[dfd] -= 1
            if s.towers[dfd] > 0:
                res.update(outcome="tower_down", towers_left=s.towers[dfd])
                return lambda: st.BattleQuestionState(self)  # осада продолжается, пока атакующий не ошибётся
            # последняя башня: забираем всё — очки и земли, соперник выбывает
            gained = D.score
            A.score += gained
            D.score = 0
            for t in s.owned_by(dfd):
                s.territories[t] = atk
            del s.capitals[dfd]
            D.eliminated = True
            res.update(outcome="castle_destroyed", points=gained, towers_left=0)
        elif captured:
            value = s.values.get(tgt, 0)
            gain = max(cfg.capture_value, value)  # руины замка стоят 1000 — и отбирают 1000
            A.score += gain
            D.score -= value
            s.values[tgt] = gain
            s.territories[tgt] = atk
            if not s.owned_by(dfd):
                D.eliminated = True
            res.update(outcome="captured", points=gain, lost=value)
        else:
            if defense_bonus:
                D.score += cfg.defense_bonus
                res["bonus"] = cfg.defense_bonus
            res["outcome"] = "defended"
        s.battle = None
        return self.next_turn

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
        # очки копились по ходу матча; при равенстве выше — победитель финальной угадайки
        ranked = sorted(s.players.values(), key=lambda p: (
            -p.score, p.tg_id != s.winner_tg_id, -len(owned[p.tg_id]), self.rng.random()))
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
