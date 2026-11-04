"""Реестр матчей процесса и матчмейкинг: по одному открытому лобби на пару (тема, карта)."""

from __future__ import annotations

import logging

from app.game.engine import MatchEngine
from app.game.services import EngineDeps
from app.game.map_topology import resolve as resolve_map
from app.game.topics import resolve as resolve_topic

log = logging.getLogger(__name__)


class MatchManager:
    def __init__(self, deps: EngineDeps):
        self.deps = deps
        self.engines: dict[str, MatchEngine] = {}
        self.player_match: dict[int, str] = {}
        self._lobbies: dict[tuple[str, str], str] = {}  # (topic_id, map_id) -> match_id открытого лобби

    def get(self, match_id: str) -> MatchEngine | None:
        return self.engines.get(match_id)

    def active_match_of(self, pid: int) -> MatchEngine | None:
        mid = self.player_match.get(pid)
        engine = self.engines.get(mid) if mid else None
        return engine if engine and not engine.finished.is_set() else None

    def _create(self, topic: str, map_id: str, deps: EngineDeps | None = None) -> MatchEngine:
        engine = MatchEngine(deps or self.deps, on_finished=self._on_finished, topic=topic, map_id=map_id)
        self.engines[engine.match_id] = engine
        engine.start()
        return engine

    async def find_match(
        self, pid: int, username: str, topic: str | None = None, map_id: str | None = None
    ) -> MatchEngine:
        """Вернуть текущий матч игрока (переподключение) или посадить его в лобби темы и карты."""
        if engine := self.active_match_of(pid):
            return engine
        key = (resolve_topic(topic).id, resolve_map(map_id).id)
        lobby_id = self._lobbies.get(key)
        lobby = self.engines.get(lobby_id) if lobby_id else None
        if lobby is None or not await lobby.request_join(pid, username):
            lobby = self._create(*key)
            self._lobbies[key] = lobby.match_id
            await lobby.request_join(pid, username)
        self.player_match[pid] = lobby.match_id
        return lobby

    async def create_bot_match(
        self, pid: int, username: str, deps: EngineDeps | None = None, topic: str | None = None,
        map_id: str | None = None,
    ) -> MatchEngine:
        """Тестовый матч: 1 человек + боты сразу, без ожидания лобби."""
        if engine := self.active_match_of(pid):
            return engine
        engine = self._create(resolve_topic(topic).id, resolve_map(map_id).id, deps)
        await engine.request_join(pid, username)
        engine.request_fill_bots()
        self.player_match[pid] = engine.match_id
        return engine

    def _on_finished(self, engine: MatchEngine) -> None:
        for pid in engine.state.players:
            if self.player_match.get(pid) == engine.match_id:
                del self.player_match[pid]
        for key, mid in list(self._lobbies.items()):
            if mid == engine.match_id:
                del self._lobbies[key]
        # сам MatchState ещё час живёт в Redis (TTL) — для экрана итогов/повторного запроса
        self.engines.pop(engine.match_id, None)

    async def shutdown(self) -> None:
        for engine in list(self.engines.values()):
            await engine.stop()
