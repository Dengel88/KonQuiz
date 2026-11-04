"""Сокеты игроков по матчам. На каждый матч — одна задача-«насос»: читает шину и раздаёт события."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import WebSocket

from app.game.engine import MatchEngine
from app.game.schemas import public_view

log = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self) -> None:
        self.sockets: dict[str, dict[int, WebSocket]] = {}
        self._pumps: dict[str, asyncio.Task] = {}

    async def connect(self, engine: MatchEngine, pid: int, ws: WebSocket) -> None:
        mid = engine.match_id
        room = self.sockets.setdefault(mid, {})
        old = room.get(pid)
        room[pid] = ws
        if old is not None and old is not ws:
            await self._safe_close(old, 4000, "Открыто новое подключение")
        if mid not in self._pumps:
            self._pumps[mid] = asyncio.create_task(self._pump(engine))
        engine.set_presence(pid, True)
        # полный снимок сразу — клиенту не нужно ждать следующего события
        await self._send(ws, {"type": "welcome", "you": pid, "state": public_view(engine.state)})

    def disconnect(self, engine: MatchEngine, pid: int, ws: WebSocket) -> None:
        room = self.sockets.get(engine.match_id, {})
        if room.get(pid) is ws:
            del room[pid]
            engine.set_presence(pid, False)

    async def _pump(self, engine: MatchEngine) -> None:
        mid = engine.match_id
        q = engine.bus.subscribe()
        try:
            while True:
                event = await q.get()
                room = self.sockets.get(mid, {})
                if event["type"] == "private":
                    if ws := room.get(event["to"]):
                        await self._send(ws, event["data"])
                    continue
                for ws in list(room.values()):
                    await self._send(ws, event)
                if event["type"] == "end":
                    for ws in list(room.values()):
                        await self._safe_close(ws, 1000, "Матч завершён")
                    return
        finally:
            engine.bus.unsubscribe(q)
            self.sockets.pop(mid, None)
            self._pumps.pop(mid, None)

    @staticmethod
    async def _send(ws: WebSocket, data: dict[str, Any]) -> None:
        try:
            await ws.send_json(data)
        except Exception:
            pass  # сокет уже умер — обработчик receive сам вызовет disconnect

    @staticmethod
    async def _safe_close(ws: WebSocket, code: int, reason: str) -> None:
        try:
            await ws.close(code=code, reason=reason)
        except Exception:
            pass
