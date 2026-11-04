"""Банк вопросов: app/questions/data/*.json, одна строка — один вопрос.

Поля записи:
  key        — постоянный id («general_choice-005»); по нему seed обновляет вопрос в базе,
               поэтому текст можно править, а ключ — никогда (новый вопрос = новый ключ)
  type       — CHOICE (1 из 4) или EXACT (число)
  category, difficulty (1..3), text, fact
  correct    — CHOICE: строка; EXACT: неотрицательное целое (на клавиатуре нет минуса и запятой)
  wrong      — только CHOICE: 3 неправильных варианта
  is_year    — только EXACT: ответ — год (боты ошибаются на ±15 лет)
  group      — сюжет («turing», «titanic»): в одном матче не больше одного вопроса группы,
               иначе факт или текст одного вопроса подсказывает ответ на другой

Удалить вопрос = убрать строку: seed пометит его в базе неактивным (оценки игроков сохранятся).
Для «Крипты» и «ИИ» — только история и устройство, никаких курсов и «самых новых моделей».
"""

import json
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
BANK_FILES = ("general", "crypto", "ai")


def load_bank(name: str) -> list[dict]:
    return json.loads((DATA_DIR / f"{name}.json").read_text(encoding="utf-8"))


def load_all() -> list[dict]:
    return [q for name in BANK_FILES for q in load_bank(name)]


def load_legacy_texts() -> dict[str, str]:
    """key -> текст вопроса до аудита 2026-10-01. Нужен один раз: связать старые строки базы
    (без ключа) с ключами, даже если текст вопроса потом исправили."""
    return json.loads((DATA_DIR / "legacy_texts.json").read_text(encoding="utf-8"))
