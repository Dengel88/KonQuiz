"""Сквозной прогон: 1 человек + 2 бота, ускоренные таймеры."""

import asyncio
import random

import pytest
from sqlalchemy import select

from app.game.bots import BotBrain
from app.game.engine import MatchEngine
from app.game.map_topology import MAPS
from app.models import Match, MatchParticipant, User

HUMAN = 1001


async def run_match(deps, autopilot: bool, map_id: str | None = None) -> MatchEngine:
    await deps.economy.upsert_user(HUMAN, "human")
    engine = MatchEngine(deps, rng=random.Random(7), map_id=map_id)
    engine.start()
    assert await engine.request_join(HUMAN, "human")
    engine.request_fill_bots()
    pilot = asyncio.create_task(BotBrain(engine, HUMAN, random.Random(1)).run()) if autopilot else None
    try:
        await asyncio.wait_for(engine.finished.wait(), timeout=60)
    finally:
        if pilot:
            pilot.cancel()
        await engine.stop()
    return engine


def check_final(engine: MatchEngine) -> None:
    s = engine.state
    assert s.state_name == "END_GAME"
    assert len(s.players) == 3 and sum(p.is_bot for p in s.players.values()) == 2
    assert all(owner is not None for owner in s.territories.values())
    results = s.final["results"]
    assert [r["place"] for r in results] == [1, 2, 3]
    assert results == sorted(results, key=lambda r: -r["score"])
    # батлы действительно шли: 5 раундов по 3 хода (если никто не выбыл раньше)
    assert s.round >= 1


@pytest.mark.parametrize("autopilot", [True, False], ids=["human-plays", "human-afk"])
async def test_full_match(deps, sm, autopilot):
    engine = await run_match(deps, autopilot)
    check_final(engine)

    human = next(r for r in engine.state.final["results"] if r["tg_id"] == HUMAN)
    async with sm() as s:
        user = await s.get(User, HUMAN)
        assert user.gold == 100 + human["gold"]
        assert user.xp == human["xp"]
        assert await s.get(Match, engine.match_id) is not None
        rows = (await s.execute(select(MatchParticipant).where(MatchParticipant.match_id == engine.match_id))).scalars().all()
        assert len(rows) == 3 and sum(r.is_bot for r in rows) == 2

    saved = await deps.store.load(engine.match_id)
    assert saved is not None and saved.state_name == "END_GAME"


@pytest.mark.parametrize("map_id", list(MAPS))
async def test_full_match_on_every_map(deps, map_id):
    engine = await run_match(deps, autopilot=True, map_id=map_id)
    assert engine.state.map_id == map_id
    assert set(engine.state.territories) == set(MAPS[map_id].territories)
    check_final(engine)
