"""Точечные правила: бой, тайбрейкер, подсказки, устаревшие действия. Движок гоняем вручную через process()."""

import random
import time

import pytest
from sqlalchemy import update

from app.game import states as st
from app.game.engine import MatchEngine
from app.game.map_topology import resolve as resolve_map
from app.models import User
from tests.conftest import make_deps

A, D, C = 1, 2, 3  # атакующий, защитник, третий

# Клетки берём из карты по умолчанию, а не хардкодим номера
MAP = resolve_map(None).territories
neighbors = resolve_map(None).neighbors
SRC = max(MAP, key=lambda t: len(neighbors(t)))
OWN, TGT = neighbors(SRC)[:2]
FAR = next(t for t in MAP if t != SRC and t not in neighbors(SRC) and t not in (OWN, TGT))


async def setup_board(sm, **overrides) -> MatchEngine:
    deps = make_deps(sm, reveal_time=5.0, **overrides)  # REVEAL держим, чтобы видеть промежуточные итоги
    for pid in (A, D, C):
        await deps.economy.upsert_user(pid, f"p{pid}")
    e = MatchEngine(deps, rng=random.Random(3))
    for pid in (A, D, C):
        e._add_player(pid, f"p{pid}", is_bot=False)
    s = e.state
    # A: SRC и OWN; D: TGT (столица) и FAR (не сосед SRC); остальное — C
    for tid in s.territories:
        s.territories[tid] = C
    s.territories[SRC] = s.territories[OWN] = A
    s.territories[TGT] = s.territories[FAR] = D
    s.capitals = {A: SRC, D: TGT, C: next(t for t, o in s.territories.items() if o == C)}
    s.turn_order, s.round, s.turn_index, s.current_turn_tg_id = [A, D, C], 1, 0, A
    await e._enter(st.BattleWaitState(e, A))
    return e


def drain(q) -> list[dict]:
    out = []
    while not q.empty():
        out.append(q.get_nowait())
    return out


async def act(e: MatchEngine, pid: int, payload: dict) -> None:
    await e.process(("action", pid, payload, time.time()))


async def attack(e: MatchEngine) -> None:
    await act(e, A, {"source_territory": SRC, "target_territory": TGT})
    assert e.state.state_name == "BATTLE_QUESTION"
    assert e.state.battle == {"attacker": A, "defender": D, "source": SRC, "target": TGT}


async def test_attack_validation(sm):
    e = await setup_board(sm)
    q = e.bus.subscribe()
    await act(e, D, {"source_territory": TGT, "target_territory": SRC})  # не его ход
    await act(e, A, {"source_territory": TGT, "target_territory": SRC})  # не своя территория
    await act(e, A, {"source_territory": SRC, "target_territory": OWN})  # своя цель
    await act(e, A, {"source_territory": SRC, "target_territory": FAR})  # не соседи
    errors = [ev for ev in drain(q) if ev["type"] == "private" and ev["data"]["type"] == "error"]
    assert len(errors) == 4
    assert e.state.state_name == "BATTLE_WAIT"
    await attack(e)


async def test_attacker_right_defender_wrong_captures_capital(sm):
    e = await setup_board(sm)
    await attack(e)
    right = e.state.current_question["correct"]
    await act(e, A, {"action": "answer", "value": right})
    await act(e, D, {"action": "answer", "value": (right + 1) % 4})
    assert e.state.state_name == "REVEAL"
    assert e.state.last_result["outcome"] == "captured"
    assert e.state.territories[TGT] == A
    assert D not in e.state.capitals  # столица потеряна → бонус в конце не получит


@pytest.mark.parametrize("a_ok, d_ok", [(False, True), (False, False)])
async def test_defender_holds(sm, a_ok, d_ok):
    e = await setup_board(sm)
    await attack(e)
    right = e.state.current_question["correct"]
    await act(e, A, {"action": "answer", "value": right if a_ok else (right + 1) % 4})
    await act(e, D, {"action": "answer", "value": right if d_ok else (right + 2) % 4})
    assert e.state.last_result["outcome"] == "defended"
    assert e.state.territories[TGT] == D


async def test_both_right_goes_to_tiebreaker(sm):
    e = await setup_board(sm)
    await attack(e)
    right = e.state.current_question["correct"]
    await act(e, D, {"action": "answer", "value": right})
    await act(e, A, {"action": "answer", "value": right})  # позже, но это неважно — решает тайбрейкер
    assert e.state.state_name == "REVEAL"
    assert e.state.last_result["outcome"] == "tiebreaker"
    await e.process(("timeout", e._timer_token))
    assert e.state.state_name == "BATTLE_TIEBREAKER"
    correct = e.state.current_question["correct"]
    await act(e, D, {"action": "answer", "value": correct + 50})
    await act(e, A, {"action": "answer", "value": correct - 10})
    assert e.state.last_result["outcome"] == "captured"
    assert e.state.territories[TGT] == A


async def test_timeout_means_no_answer(sm):
    e = await setup_board(sm)
    await attack(e)
    right = e.state.current_question["correct"]
    await act(e, A, {"action": "answer", "value": right})
    await e.process(("timeout", e._timer_token))  # защитник промолчал
    assert e.state.territories[TGT] == A


async def test_stale_phase_and_old_timer_ignored(sm):
    e = await setup_board(sm)
    old_phase, old_token = e.state.phase, e._timer_token
    await attack(e)
    await e.process(("timeout", old_token))  # таймер прошлой фазы
    assert e.state.state_name == "BATTLE_QUESTION"
    q = e.bus.subscribe()
    await act(e, A, {"action": "answer", "value": 0, "phase": old_phase})
    assert A not in e.state.answers
    assert any(ev["type"] == "private" and "устарело" in ev["data"]["message"] for ev in drain(q))


async def test_hints(sm):
    e = await setup_board(sm)
    await attack(e)
    q = e.bus.subscribe()

    # 50/50 — из запаса, результат только атакующему
    await act(e, A, {"use_hint": "50_50"})
    hint = [ev for ev in drain(q) if ev["type"] == "private"][0]
    assert hint["to"] == A and hint["data"]["paid_with"] == "inventory"
    assert e.state.current_question["correct"] not in hint["data"]["remove"]
    assert len(hint["data"]["remove"]) == 2

    # повторно в том же матче — нельзя
    await act(e, A, {"use_hint": "50_50"})
    assert "уже использована" in drain(q)[0]["data"]["message"]

    # заморозка: запас пуст → платим золотом, таймер +10 с
    async with sm.begin() as s:
        await s.execute(update(User).where(User.id == A).values(hints_freeze=0))
    before = e.state.timer_ends_at
    await act(e, A, {"use_hint": "freeze"})
    events = drain(q)
    assert [ev for ev in events if ev["type"] == "private"][0]["data"]["paid_with"] == "gold"
    assert e.state.timer_ends_at == pytest.approx(before + 10)
    assert (await e.deps.economy.get_user(A)).gold == 80

    # радар: сумма 100, правильный ~65
    await act(e, D, {"use_hint": "radar"})
    dist = [ev for ev in drain(q) if ev["type"] == "private"][0]["data"]["distribution"]
    assert sum(dist) == 100 and 50 <= dist[e.state.current_question["correct"]] <= 80

    # нет ни запаса, ни золота
    async with sm.begin() as s:
        await s.execute(update(User).where(User.id == D).values(hints_50_50=0, gold=10))
    await act(e, D, {"use_hint": "50_50"})
    assert "не хватает золота" in drain(q)[0]["data"]["message"]


async def test_choice_hints_rejected_on_exact(sm):
    e = await setup_board(sm)
    await e._enter(st.ExpansionQuestionState(e, [A, D, C]))
    q = e.bus.subscribe()
    await act(e, A, {"use_hint": "radar"})
    assert "вариантами" in drain(q)[0]["data"]["message"]
    assert (await e.deps.economy.get_user(A)).hints_radar == 3  # ничего не списали
