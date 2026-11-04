import random
import time

from sqlalchemy import select

from app.game import states as st
from app.game.engine import MatchEngine
from app.game.schemas import public_view
from app.models import QType, Question


async def test_topic_questions_and_fact_reveal(deps, sm):
    e = MatchEngine(deps, rng=random.Random(1), topic="crypto")
    for pid in (1, 2, 3):
        e._add_player(pid, f"p{pid}", is_bot=False)
    assert e.state.topic == "crypto"

    await e._enter(st.ExpansionQuestionState(e, [1, 2, 3]))
    cq = e.state.current_question
    assert cq["category"] == "Крипта" and cq["fact"]
    assert "fact" not in public_view(e.state)["current_question"]  # факт часто содержит ответ

    for pid in (1, 2, 3):
        await e.process(("action", pid, {"action": "answer", "value": 1}, time.time()))
    assert e.state.last_result["fact"] == cq["fact"]


async def test_topic_falls_back_to_general_when_exhausted(deps, sm):
    async with sm() as s:
        crypto_exact = (await s.execute(
            select(Question.id).where(Question.category == "Крипта", Question.q_type == QType.EXACT)
        )).scalars().all()
    q = await deps.questions.pick(QType.EXACT, list(crypto_exact), ("Крипта",))
    assert q.category != "Крипта"  # тема исчерпана — новый вопрос из общего банка, а не повтор


async def test_unknown_topic_is_general(deps):
    e = MatchEngine(deps, topic="nonsense")
    assert e.state.topic == "general"
