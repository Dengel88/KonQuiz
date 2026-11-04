"""Темы матча. Тема = набор категорий вопросов; None — все вопросы банка.

Если в теме кончились неиспользованные вопросы нужного типа, движок добирает из общего
банка (в «Крипте» и «ИИ» устойчивых числовых фактов мало) — см. QuestionRepo.pick.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Topic:
    id: str
    title: str
    categories: tuple[str, ...] | None


TOPICS: dict[str, Topic] = {
    t.id: t
    for t in (
        Topic("general", "Общая", None),
        Topic("history", "История", ("История",)),
        Topic("geography", "География", ("География",)),
        Topic("crypto", "Крипта", ("Крипта",)),
        Topic("ai", "ИИ", ("ИИ",)),
    )
}
DEFAULT_TOPIC = "general"


def resolve(topic_id: str | None) -> Topic:
    return TOPICS.get(topic_id or DEFAULT_TOPIC, TOPICS[DEFAULT_TOPIC])
