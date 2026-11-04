import random
import time

from sqlalchemy import select

from app.game import states as st
from app.game.engine import MatchEngine
from app.models import QuestionRating


async def test_result_carries_question_id_and_rating_upserts(deps, sm):
    e = MatchEngine(deps, rng=random.Random(2))
    for pid in (1, 2, 3):
        await deps.economy.upsert_user(pid, f"p{pid}")
        e._add_player(pid, f"p{pid}", is_bot=False)
    await e._enter(st.ExpansionQuestionState(e, [1, 2, 3]))
    qid = e.state.current_question["id"]
    for pid in (1, 2, 3):
        await e.process(("action", pid, {"action": "answer", "value": 1}, time.time()))
    assert e.state.last_result["question_id"] == qid

    assert await deps.questions.rate(1, qid, 1)
    assert await deps.questions.rate(1, qid, -1)  # передумал — перезапись, не вторая строка
    assert await deps.questions.rate(2, qid, 0)
    assert not await deps.questions.rate(1, 10**9, 1)
    async with sm() as s:
        rows = (await s.execute(select(QuestionRating).where(QuestionRating.question_id == qid))).scalars().all()
    assert sorted((r.user_id, r.value) for r in rows) == [(1, -1), (2, 0)]
