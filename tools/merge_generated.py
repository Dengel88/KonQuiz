"""Слить проверенные новые вопросы в банк.

python tools/merge_generated.py review/generated/tech.verified.json [ещё файлы...]

- банк по категории: «ИИ» -> ai.json, «Крипта» -> crypto.json, остальное -> general.json;
- постоянный ключ: следующий номер (ai-120, crypto-127, general_choice-203, general_exact-161…);
- `group` внутри партии и `related` (ключи банка) -> общие группы; если связываются вопросы из
  разных существующих групп, группы объединяются под одним именем;
- `related` в банк не пишется, `sources` сохраняется;
- review/generated/merged_keys.json помнит «временный ключ -> постоянный»: повторный запуск
  того же файла ничего не задвоит.
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "app" / "questions" / "data"
LOG = ROOT / "review" / "generated" / "merged_keys.json"
BANKS = ("general", "crypto", "ai")


def bank_of(q: dict) -> str:
    return {"ИИ": "ai", "Крипта": "crypto"}.get(q["category"], "general")


def prefix_of(q: dict) -> str:
    bank = bank_of(q)
    return f"general_{q['type'].lower()}" if bank == "general" else bank


def dump(path: Path, qs: list[dict]) -> None:
    path.write_text("[\n" + ",\n".join(json.dumps(q, ensure_ascii=False) for q in qs) + "\n]\n", encoding="utf-8")


def main(files: list[str]) -> None:
    banks = {b: json.loads((DATA / f"{b}.json").read_text(encoding="utf-8")) for b in BANKS}
    by_key = {q["key"]: q for qs in banks.values() for q in qs}
    log: dict[str, str] = json.loads(LOG.read_text(encoding="utf-8")) if LOG.exists() else {}

    next_n: dict[str, int] = {}
    for key in by_key:
        m = re.fullmatch(r"(.+)-(\d+)", key)
        next_n[m[1]] = max(next_n.get(m[1], 0), int(m[2]))

    # union-find по ключам банка: связи из `group` партии и из `related`
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        parent[find(a)] = find(b)

    added = 0
    local_name: dict[str, str] = {}  # постоянный ключ -> имя группы из партии («kaissa»)
    for f in files:
        batch = json.loads(Path(f).read_text(encoding="utf-8"))
        local_groups: dict[str, list[str]] = {}
        for q in batch:
            tmp = q["key"]
            if tmp in log:
                continue  # уже влит раньше
            p = prefix_of(q)
            next_n[p] += 1
            key = f"{p}-{next_n[p]:03d}"
            log[tmp] = key
            new = {k: v for k, v in q.items() if k not in ("related", "group")}
            new["key"] = key
            new["group"] = None
            banks[bank_of(q)].append(new)
            by_key[key] = new
            added += 1
            if q.get("group"):
                local_groups.setdefault(f"{f}:{q['group']}", []).append(key)
                local_name[key] = q["group"]
            for r in q.get("related") or []:
                if r in by_key:
                    union(key, r)
        for members in local_groups.values():
            for m in members[1:]:
                union(members[0], m)

    # уже существующие группы тоже участвуют: всё, что в одной группе, — один кластер
    by_group: dict[str, list[str]] = {}
    for k, q in by_key.items():
        if q.get("group"):
            by_group.setdefault(q["group"], []).append(k)
    for members in by_group.values():
        for m in members[1:]:
            union(members[0], m)

    clusters: dict[str, list[str]] = {}
    for k in list(parent):
        clusters.setdefault(find(k), []).append(k)
    for members in clusters.values():
        if len(members) < 2:
            continue
        # имя: группа банка → имя из партии → по ключу
        names = sorted({by_key[m]["group"] for m in members if by_key[m].get("group")})
        names = names or sorted({local_name[m] for m in members if m in local_name})
        name = names[0] if names else "g_" + min(members).replace("-", "_")
        for m in members:
            by_key[m]["group"] = name

    for b, qs in banks.items():
        # group и interest/sources — в конце строки, как в остальном банке
        ordered = []
        for q in qs:
            head = {k: v for k, v in q.items() if k not in ("group", "interest", "sources")}
            tail = {k: q[k] for k in ("interest", "sources") if k in q}
            ordered.append({**head, "group": q.get("group"), **tail})
        dump(DATA / f"{b}.json", ordered)
    LOG.write_text(json.dumps(log, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"добавлено {added}; всего в банке {sum(len(v) for v in banks.values())}")


if __name__ == "__main__":
    main(sys.argv[1:])
