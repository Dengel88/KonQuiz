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


async def setup_board(sm, rnd: int = 2, **overrides) -> MatchEngine:
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
    s.towers = {pid: 3 for pid in (A, D, C)}
    s.values = {tid: (1000 if tid in s.capitals.values() else 200) for tid in s.territories}
    for pid in (A, D, C):
        s.players[pid].score = sum(s.values[t] for t in s.owned_by(pid))
    s.rounds_total = 4
    s.turn_order, s.round, s.turn_index, s.current_turn_tg_id = [A, D, C], rnd, 0, A
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
    await act(e, A, {"target_territory": FAR})  # не граничит ни с одной землёй A
    errors = [ev for ev in drain(q) if ev["type"] == "private" and ev["data"]["type"] == "error"]
    assert len(errors) == 4
    assert e.state.state_name == "BATTLE_WAIT"
    await attack(e)


async def answer(e, a_ok: bool, d_ok: bool) -> None:
    right = e.state.current_question["correct"]
    await act(e, A, {"action": "answer", "value": right if a_ok else (right + 1) % 4})
    await act(e, D, {"action": "answer", "value": right if d_ok else (right + 2) % 4})


async def next_phase(e) -> None:
    await e.process(("timeout", e._timer_token))


async def test_castle_siege_three_towers_then_takes_everything(sm):
    e = await setup_board(sm)
    s = e.state
    d_score = s.players[D].score  # замок 1000 + FAR 200
    a_score = s.players[A].score
    await attack(e)
    for left in (2, 1):
        await answer(e, True, False)
        assert s.last_result["outcome"] == "tower_down" and s.towers[D] == left
        assert s.territories[TGT] == D  # пока стоит хоть одна башня — замок его
        await next_phase(e)
        assert s.state_name == "BATTLE_QUESTION"  # осада продолжается без нового выбора цели
    await answer(e, True, False)
    assert s.last_result["outcome"] == "castle_destroyed"
    assert s.territories[TGT] == A and s.territories[FAR] == A  # забрал все земли
    assert s.players[A].score == a_score + d_score and s.players[D].score == 0
    assert s.players[D].eliminated and D not in s.capitals


async def test_siege_stops_on_first_miss_and_towers_stay_down(sm):
    e = await setup_board(sm)
    await attack(e)
    await answer(e, True, False)
    await next_phase(e)
    await answer(e, False, True)
    assert e.state.last_result["outcome"] == "defended"
    assert e.state.towers[D] == 2  # упавшая башня не встаёт
    await next_phase(e)
    assert e.state.state_name == "BATTLE_WAIT" and e.state.current_turn_tg_id == D


async def test_capture_scoring(sm):
    e = await setup_board(sm)
    s = e.state
    c_land = next(t for t in e.attack_targets(A) if s.territories[t] == C and not e.is_castle(t))
    a0, c0 = s.players[A].score, s.players[C].score
    await act(e, A, {"target_territory": c_land})
    right = s.current_question["correct"]
    await act(e, A, {"action": "answer", "value": right})
    await act(e, C, {"action": "answer", "value": (right + 1) % 4})
    assert s.last_result["outcome"] == "captured"
    assert s.players[A].score == a0 + 400 and s.players[C].score == c0 - 200
    assert s.values[c_land] == 400


async def test_defense_bonus_only_for_right_answer(sm):
    e = await setup_board(sm)
    d0 = e.state.players[D].score
    await attack(e)
    await answer(e, False, True)
    assert e.state.players[D].score == d0 + 100
    e = await setup_board(sm)
    d0 = e.state.players[D].score
    await attack(e)
    await answer(e, False, False)
    assert e.state.players[D].score == d0


async def test_round_rules_for_targets(sm):
    e = await setup_board(sm, rnd=1)
    assert TGT not in e.state.attack_targets  # раунд 1: замки нельзя
    q = e.bus.subscribe()
    await act(e, A, {"target_territory": TGT})
    assert "первом раунде" in drain(q)[0]["data"]["message"]
    e.state.round = 2
    assert TGT in e.attack_targets(A)
    e.state.round = 4
    assert FAR in e.attack_targets(A)  # последний раунд — любая вражеская земля
    assert e.pick_source(A, FAR) in e.state.owned_by(A)


@pytest.mark.parametrize("a_ok, d_ok", [(False, True), (False, False)])
async def test_defender_holds(sm, a_ok, d_ok):
    e = await setup_board(sm)
    await attack(e)
    right = e.state.current_question["correct"]
    await act(e, A, {"action": "answer", "value": right if a_ok else (right + 1) % 4})
    await act(e, D, {"action": "answer", "value": right if d_ok else (right + 2) % 4})
    assert e.state.last_result["outcome"] == "defended"
    assert e.state.territories[TGT] == D and e.state.towers[D] == 3


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
    assert e.state.last_result["outcome"] == "tower_down"
    assert e.state.towers[D] == 2


async def test_timeout_means_no_answer(sm):
    e = await setup_board(sm)
    await attack(e)
    right = e.state.current_question["correct"]
    await act(e, A, {"action": "answer", "value": right})
    await e.process(("timeout", e._timer_token))  # защитник промолчал
    assert e.state.last_result["outcome"] == "tower_down"


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


async def fresh_engine(sm) -> MatchEngine:
    deps = make_deps(sm, reveal_time=5.0)
    e = MatchEngine(deps, rng=random.Random(5))
    for pid in (A, D, C):
        e._add_player(pid, f"p{pid}", is_bot=False)
    return e


async def test_random_capitals_not_adjacent_and_worth_1000(sm):
    e = await fresh_engine(sm)
    for pid, tid in e.assign_capitals():
        e.place_capital(pid, tid)
    caps = list(e.state.capitals.values())
    assert len(set(caps)) == 3
    assert all(b not in e.map.neighbors(a) for a in caps for b in caps if a != b)
    assert all(p.score == 1000 for p in e.state.players.values())
    assert e.state.towers == {A: 3, D: 3, C: 3}


async def test_expansion_winner_takes_two_second_one(sm):
    e = await fresh_engine(sm)
    for pid, tid in e.assign_capitals():
        e.place_capital(pid, tid)
    s = e.state
    await e._enter(st.ExpansionQuestionState(e, [A, D, C]))
    right = s.current_question["correct"]
    await act(e, D, {"action": "answer", "value": right + 1})   # 2-е место
    await act(e, A, {"action": "answer", "value": right})       # 1-е
    await act(e, C, {"action": "answer", "value": right + 99})  # 3-е — ничего
    assert s.last_result["picks"] == {str(A): 2, str(D): 1}
    await next_phase(e)
    picks = []
    while s.state_name == "EXPANSION_PICK":
        picks.append(s.picker_tg_id)
        await act(e, s.picker_tg_id, {"action": "pick", "territory": s.pick_options[0]})
    assert picks == [A, A, D]
    assert s.players[A].score == 1400 and s.players[D].score == 1200 and s.players[C].score == 1000


async def test_tie_on_top_goes_to_final_guess(sm):
    e = await setup_board(sm)
    s = e.state
    for p in s.players.values():
        p.score = 1500
    s.players[C].score = 900
    s.round, s.turn_index = s.rounds_total, len(s.turn_order)
    await e._enter(e.next_turn())
    assert s.state_name == "FINAL_TIEBREAKER" and set(s.question_participants) == {A, D}
    right = s.current_question["correct"]
    await act(e, A, {"action": "answer", "value": right + 5})
    await act(e, D, {"action": "answer", "value": right})
    assert s.winner_tg_id == D
    await next_phase(e)
    await e._advance()
    places = [r["tg_id"] for r in s.final["results"]]
    assert places[0] == D


async def test_last_round_leader_attacks_first(sm):
    e = await setup_board(sm)
    s = e.state
    s.players[C].score, s.players[A].score, s.players[D].score = 5000, 100, 2000
    s.round, s.turn_index = s.rounds_total - 1, len(s.turn_order)
    e.next_turn()
    assert s.round == s.rounds_total and s.turn_order == [C, D, A]
