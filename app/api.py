import asyncio
import dataclasses
import json
import logging
import random

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from app.auth import AuthError, TgUser, authenticate
from app.config import Settings
from app.deps import current_user, get_connections, get_economy, get_manager, get_settings_dep, get_store
from app.game.bots import BotBrain
from app.game.manager import MatchManager
from app.game.map_topology import MAPS
from app.game.map_topology import resolve as resolve_map
from app.game.schemas import public_view
from app.game.services import Economy, MatchStore
from app.game.topics import TOPICS
from app.game.topics import resolve as resolve_topic
from app.ws.connections import ConnectionManager

log = logging.getLogger(__name__)

router = APIRouter()
test_router = APIRouter(prefix="/api/test", tags=["test"])


@router.get("/api/health")
async def health(manager: MatchManager = Depends(get_manager)) -> dict:
    return {"ok": True, "active_matches": len(manager.engines)}


@router.get("/api/map")
async def game_map(map_id: str | None = None) -> dict:
    """Геометрия и соседство карты; без map_id — карта по умолчанию."""
    return resolve_map(map_id).public()


@router.get("/api/maps")
async def maps() -> list[dict]:
    return [{"id": m.id, "title": m.title} for m in MAPS.values()]


@router.get("/api/topics")
async def topics(manager: MatchManager = Depends(get_manager)) -> list[dict]:
    counts = await manager.deps.questions.count_by_category()
    total = sum(counts.values())
    return [
        {"id": t.id, "title": t.title,
         "questions": total if t.categories is None else sum(counts.get(c, 0) for c in t.categories)}
        for t in TOPICS.values()
    ]


@router.get("/api/fact")
async def fact(topic: str | None = None, manager: MatchManager = Depends(get_manager)) -> dict:
    """Случайный «интересный факт» по теме — из того же банка, из которого берутся вопросы."""
    text = await manager.deps.questions.random_fact(resolve_topic(topic).categories)
    return {"fact": text}


@router.get("/api/me")
async def me(
    user: TgUser = Depends(current_user),
    economy: Economy = Depends(get_economy),
    manager: MatchManager = Depends(get_manager),
) -> dict:
    u = await economy.get_user(user.id)
    active = manager.active_match_of(user.id)
    return {
        "id": u.id, "username": u.username, "gold": u.gold, "xp": u.xp,
        "hints": {"50_50": u.hints_50_50, "freeze": u.hints_freeze, "radar": u.hints_radar},
        "active_match_id": active.match_id if active else None,
    }


class RateIn(BaseModel):
    value: int = Field(ge=-1, le=1)  # 1 нравится, 0 средне, -1 не нравится


@router.post("/api/questions/{question_id}/rate")
async def rate_question(
    question_id: int,
    body: RateIn,
    user: TgUser = Depends(current_user),
    manager: MatchManager = Depends(get_manager),
) -> dict:
    if not await manager.deps.questions.rate(user.id, question_id, body.value):
        raise HTTPException(404, "Вопрос не найден")
    return {"ok": True}


@router.get("/api/matches/{match_id}")
async def match_state(match_id: str, store: MatchStore = Depends(get_store)) -> dict:
    state = await store.load(match_id)
    if state is None:
        raise HTTPException(404, "Матч не найден или истёк")
    return public_view(state)


@router.websocket("/ws")
async def game_ws(
    ws: WebSocket,
    init_data: str = Query(...),
    match_id: str | None = Query(None),
    topic: str | None = Query(None),
    map_id: str | None = Query(None, alias="map"),
    settings: Settings = Depends(get_settings_dep),
    manager: MatchManager = Depends(get_manager),
    conns: ConnectionManager = Depends(get_connections),
    economy: Economy = Depends(get_economy),
) -> None:
    await ws.accept()
    try:
        user = authenticate(init_data, settings)
    except AuthError as err:
        await ws.close(code=4401, reason=str(err)[:120])
        return
    await economy.upsert_user(user.id, user.username)

    engine = manager.get(match_id) if match_id else None
    if engine is None or user.id not in engine.state.players:
        engine = await manager.find_match(user.id, user.username, topic, map_id)

    await conns.connect(engine, user.id, ws)
    try:
        while True:
            raw = await ws.receive_text()
            try:
                payload = json.loads(raw)
            except ValueError:
                await ws.send_json({"type": "error", "message": "Ожидается JSON"})
                continue
            engine.submit(user.id, payload)
    except WebSocketDisconnect:
        pass
    finally:
        conns.disconnect(engine, user.id, ws)


# ---------------------------------------------------------------- только для разработки

@test_router.post("/match")
async def test_match(
    topic: str | None = None,
    map_id: str | None = Query(None, alias="map"),
    user: TgUser = Depends(current_user),
    manager: MatchManager = Depends(get_manager),
) -> dict:
    """Матч «1 человек + 2 бота». Дальше подключайтесь к /ws?init_data=...&match_id=..."""
    engine = await manager.create_bot_match(user.id, user.username, topic=topic, map_id=map_id)
    return {"match_id": engine.match_id}


FAST = dict(
    matchmaking_timeout=0.05, exact_question_time=0.3, choice_question_time=0.3, pick_time=0.2,
    attack_choice_time=0.2, reveal_time=0.0, realm_reveal_time=0.0, bot_delay_min=0.01, bot_delay_max=0.05,
    bot_pick_delay_min=0.01, bot_pick_delay_max=0.03,
)


@test_router.post("/simulate")
async def simulate(
    user: TgUser = Depends(current_user),
    manager: MatchManager = Depends(get_manager),
    autopilot: bool = Query(True, description="false — «человек» молчит, всё решают таймауты"),
    topic: str | None = None,
    map_id: str | None = Query(None, alias="map"),
) -> dict:
    """Прогон целого матча на ускоренных таймерах. «Человек» ходит через engine.submit — как по WS."""
    fast = dataclasses.replace(manager.deps, settings=manager.deps.settings.model_copy(update=FAST))
    engine = await manager.create_bot_match(user.id, user.username, deps=fast, topic=topic, map_id=map_id)
    pilot = asyncio.create_task(BotBrain(engine, user.id, random.Random()).run()) if autopilot else None
    try:
        await asyncio.wait_for(engine.finished.wait(), timeout=120)
    except asyncio.TimeoutError:
        await engine.stop()
        raise HTTPException(500, f"Матч не завершился, застрял в {engine.state.state_name}") from None
    finally:
        if pilot:
            pilot.cancel()
    s = engine.state
    return {
        "match_id": s.match_id,
        "phases": s.phase,
        "rounds": s.round,
        "territories": s.territories,
        "capitals": s.capitals,
        "final": s.final,
    }
