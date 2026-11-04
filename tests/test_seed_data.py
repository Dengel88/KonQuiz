from collections import Counter

from app.game.topics import TOPICS
from app.questions import load_all, load_legacy_texts

BANK = load_all()


def test_keys_and_texts_unique():
    for field in ("key", "text"):
        dupes = [v for v, n in Counter(q[field] for q in BANK).items() if n > 1]
        assert not dupes, (field, dupes)


def test_shapes():
    for q in BANK:
        text = q["key"]
        assert q["type"] in ("CHOICE", "EXACT"), text
        assert q["difficulty"] in (1, 2, 3), text
        assert q["category"] and q["text"], text
        assert q.get("group") is None or (isinstance(q["group"], str) and q["group"]), text
        if q["type"] == "CHOICE":
            assert len(q["wrong"]) == 3, text
            assert len({q["correct"], *q["wrong"]}) == 4, f"повтор среди вариантов: {text}"
        else:
            value = q["correct"]
            # клавиатура в клиенте: только неотрицательные целые, до 9 цифр
            assert isinstance(value, int) and 0 <= value < 10**9, text
            if q["is_year"]:
                assert 400 <= value <= 2030, text


def test_every_question_has_fact():
    missing = [q["key"] for q in BANK if not q.get("fact")]
    assert not missing, missing[:10]


def test_legacy_texts_cover_old_bank():
    # по ним seed один раз связывает строки прод-базы (без ключа) с ключами
    assert len(load_legacy_texts()) == 602


def test_groups_are_real_clusters():
    # группа из одного вопроса бессмысленна — скорее всего, опечатка в названии группы
    sizes = Counter(q["group"] for q in BANK if q.get("group"))
    lonely = [g for g, n in sizes.items() if n < 2]
    assert not lonely, lonely


def test_topics_have_enough_questions():
    counts: Counter = Counter((q["type"], q["category"]) for q in BANK)
    for topic in TOPICS.values():
        if topic.categories is None:
            continue
        choice = sum(counts[("CHOICE", c)] for c in topic.categories)
        exact = sum(counts[("EXACT", c)] for c in topic.categories)
        # ~15 боёв с вариантами и ~17 числовых за матч; числовые при нехватке добираются из общего банка
        assert choice >= 45, (topic.id, choice)
        assert exact >= 20, (topic.id, exact)
