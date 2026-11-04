from sqlalchemy import select

from app import seed
from app.models import QType, Question, QuestionRating, User

Q = lambda key, text, group=None: {  # noqa: E731
    "key": key, "type": "CHOICE", "category": "История", "difficulty": 1, "text": text,
    "correct": "А", "wrong": ["Б", "В", "Г"], "fact": "факт", "group": group,
}


async def rows(sm) -> dict[str, Question]:
    async with sm() as s:
        return {q.key: q for q in (await s.execute(select(Question))).scalars()}


async def test_seed_binds_legacy_rows_and_keeps_ratings(sm, monkeypatch):
    # прод до миграции 0005: строка без ключа, у неё уже есть оценка игрока
    async with sm.begin() as s:
        for q in (await s.execute(select(Question))).scalars():
            await s.delete(q)
        s.add(User(id=1, username="u"))
        old = Question(q_type=QType.CHOICE, text="Старый текст?", correct_answer="А", wrong_answers=["Б", "В", "Г"])
        gone = Question(q_type=QType.CHOICE, text="Убранный?", correct_answer="А", wrong_answers=["Б", "В", "Г"])
        s.add_all([old, gone])
        await s.flush()
        s.add(QuestionRating(user_id=1, question_id=old.id, value=1))
        old_id = old.id

    # в файлах вопрос исправлен (новый текст), второй убран, третий новый
    monkeypatch.setattr(seed, "load_all", lambda: [Q("x-001", "Новый текст?"), Q("x-002", "Совсем новый?")])
    monkeypatch.setattr(seed, "load_legacy_texts", lambda: {"x-001": "Старый текст?", "x-099": "Убранный?"})
    report = await seed.seed_questions(sm)
    assert (report.added, report.updated, report.deactivated) == (1, 1, 1)

    r = await rows(sm)
    assert r["x-001"].id == old_id and r["x-001"].text == "Новый текст?"  # та же строка — оценка жива
    async with sm() as s:
        assert (await s.execute(select(QuestionRating))).scalar_one().question_id == old_id
        gone_row = (await s.execute(select(Question).where(Question.text == "Убранный?"))).scalar_one()
    assert gone_row.active is False

    # повторный запуск ничего не меняет
    again = await seed.seed_questions(sm)
    assert (again.added, again.updated, again.deactivated) == (0, 0, 0)


async def test_seed_allows_swapping_texts(sm, monkeypatch):
    monkeypatch.setattr(seed, "load_legacy_texts", lambda: {})
    monkeypatch.setattr(seed, "load_all", lambda: [Q("s-1", "Первый?"), Q("s-2", "Второй?")])
    await seed.seed_questions(sm)
    monkeypatch.setattr(seed, "load_all", lambda: [Q("s-1", "Второй?"), Q("s-2", "Первый?")])
    await seed.seed_questions(sm)  # уникальность text не должна помешать
    r = await rows(sm)
    assert (r["s-1"].text, r["s-2"].text) == ("Второй?", "Первый?")


async def test_pick_skips_group_and_inactive(sm, deps, monkeypatch):
    monkeypatch.setattr(seed, "load_legacy_texts", lambda: {})
    monkeypatch.setattr(seed, "load_all", lambda: [
        Q("g-1", "Тьюринг 1?", "turing"), Q("g-2", "Тьюринг 2?", "turing"), Q("g-3", "Другое?")])
    await seed.seed_questions(sm)  # всё остальное из банка выключится
    r = await rows(sm)
    for _ in range(20):
        q = await deps.questions.pick(QType.CHOICE, [r["g-1"].id])
        assert q.key == "g-3"  # g-2 из той же группы, остальной банк выключен
    # когда новых не осталось — допускается повтор, но выключенные не выпадают никогда
    q = await deps.questions.pick(QType.CHOICE, [r["g-1"].id, r["g-3"].id])
    assert q.active and q.key.startswith("g-")
