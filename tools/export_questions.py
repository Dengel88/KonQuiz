"""Выгрузка банка вопросов для внешней проверки достоверности.

python tools/export_questions.py  ->  review/questions.csv   (таблица: Excel / Google Sheets)
                                      review/batch_NN.md     (пачки по 50 — вставлять в ИИ-проверяльщик)
"""

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.questions import load_all  # noqa: E402

OUT = ROOT / "review"
BATCH = 50

PROMPT = """Проверь достоверность вопросов викторины. Для КАЖДОГО пункта ответь одной строкой:
`№ — OK` или `№ — ОШИБКА: что не так и как правильно (источник)`.
Проверяй: 1) правильный ответ действительно верен; 2) ни один «неправильный» вариант
не является тоже верным; 3) факт не содержит неточностей; 4) у числовых ответов —
точное значение и нет ли расхождений между авторитетными источниками.
Не пересказывай верные пункты, пиши только вердикт.
"""


def rows() -> list[dict]:
    out = []
    for q in load_all():
        choice = q["type"] == "CHOICE"
        out.append({"n": q["key"], "cat": q["category"],
                    "type": "варианты" if choice else ("год" if q["is_year"] else "число"),
                    "diff": q["difficulty"], "text": q["text"], "correct": str(q["correct"]),
                    "wrong": " | ".join(q["wrong"]) if choice else "", "fact": q.get("fact") or ""})
    return out


def main() -> None:
    OUT.mkdir(exist_ok=True)
    data = rows()
    # ; и BOM — чтобы русский Excel открыл без мастера импорта
    with open(OUT / "questions.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["№", "Категория", "Тип", "Сложность", "Вопрос", "Правильный ответ",
                    "Неправильные варианты", "Факт", "Вердикт", "Комментарий"])
        for r in data:
            w.writerow([r["n"], r["cat"], r["type"], r["diff"], r["text"], r["correct"], r["wrong"], r["fact"], "", ""])

    for old in OUT.glob("batch_*.md"):
        old.unlink()
    for b in range(0, len(data), BATCH):
        chunk = data[b:b + BATCH]
        lines = [PROMPT, ""]
        for r in chunk:
            line = f"{r['n']}. [{r['cat']}] {r['text']}\n   Ответ: {r['correct']}"
            if r["wrong"]:
                line += f"\n   Неверные варианты: {r['wrong']}"
            line += f"\n   Факт: {r['fact']}"
            lines.append(line)
        (OUT / f"batch_{b // BATCH + 1:02d}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{len(data)} вопросов -> {OUT}")


if __name__ == "__main__":
    main()
