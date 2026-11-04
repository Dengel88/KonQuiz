"""Синхронизация вопросов из app/questions/data/*.json в базу: `python -m app.seed`.

Файлы — источник правды для содержимого вопроса:
- вопрос ищется по ключу `key`; строки без ключа (база до миграции 0005) — по тексту, в том
  числе по исходному тексту из legacy_texts.json (до аудита 2026-10-01), и получают ключ;
- текст, ответы, факт, категория, сложность и группа перезаписываются из файла;
- вопрос, которого больше нет в файлах, помечается active=false (не удаляется — на нём оценки);
- отметку verified seed не трогает.
"""

import asyncio
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import get_settings
from app.db import make_engine, make_sessionmaker
from app.models import QType, Question
from app.questions import load_all, load_legacy_texts


@dataclass
class SeedReport:
    added: int = 0
    updated: int = 0
    deactivated: int = 0

    def __str__(self) -> str:
        return f"добавлено {self.added}, обновлено {self.updated}, выключено {self.deactivated}"


def _fields(q: dict) -> dict:
    is_choice = q["type"] == "CHOICE"
    return dict(
        key=q["key"],
        q_type=QType.CHOICE if is_choice else QType.EXACT,
        category=q["category"],
        difficulty=q["difficulty"],
        text=q["text"],
        correct_answer=str(q["correct"]),
        wrong_answers=q["wrong"] if is_choice else None,
        is_year=False if is_choice else q["is_year"],
        fact=q.get("fact"),
        group_key=q.get("group"),
        active=True,
    )


async def seed_questions(sm: async_sessionmaker[AsyncSession]) -> SeedReport:
    report = SeedReport()
    bank = [_fields(q) for q in load_all()]
    legacy = load_legacy_texts()
    async with sm.begin() as s:
        rows = list((await s.execute(select(Question))).scalars())
        by_key = {r.key: r for r in rows if r.key}
        by_text = {r.text: r for r in rows if not r.key}

        # Сначала находим строку для каждого вопроса из файлов, потом уводим её текст во
        # временный: text в базе уникален, и иначе обмен формулировками между вопросами упадёт.
        matched: list[tuple[dict, Question | None]] = []
        for f in bank:
            row = (by_key.get(f["key"]) or by_text.pop(f["text"], None)
                   or by_text.pop(legacy.get(f["key"], ""), None))
            matched.append((f, row))
        for f, row in matched:
            if row is not None and row.text != f["text"]:
                row.text = f"__tmp__{row.id}"
        await s.flush()

        seen: set[int] = set()
        for f, row in matched:
            if row is None:
                row = Question(**f)
                s.add(row)
                report.added += 1
            else:
                changed = any(getattr(row, k) != v for k, v in f.items() if k != "text") \
                    or row.text.startswith("__tmp__")
                for k, v in f.items():
                    setattr(row, k, v)
                report.updated += changed
            await s.flush()
            seen.add(row.id)

        for r in rows:
            if r.id not in seen and r.active:
                r.active = False
                report.deactivated += 1
    return report


async def main() -> None:
    engine = make_engine(get_settings().database_url)
    report = await seed_questions(make_sessionmaker(engine))
    await engine.dispose()
    print(f"Вопросы: {report}")


if __name__ == "__main__":
    asyncio.run(main())
