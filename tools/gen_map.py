"""Генератор карты: диаграмма Вороного на «дрожащей» сетке 3x5 + рукописные (зашумлённые) границы.

Геометрия — источник правды: соседство вычисляется из общих границ регионов, поэтому
на экране игрок видит ровно те связи, по которым сервер разрешает атаки.

Запуск: python tools/gen_map.py [seed]  ->  app/game/maps/island.json
"""

import json
import math
import random
import sys
from pathlib import Path

W, H = 600, 780  # viewBox; вертикально — под экран телефона
COLS, ROWS = 3, 5
MARGIN = 30
MIN_SHARED_EDGE = 28  # короче — считаем, что регионы касаются углом, а не граничат

NAMES = [
    "Северный Предел", "Ледяная Гавань", "Волчий Перевал",
    "Туманные Топи", "Каменный Брод", "Серебряный Кряж",
    "Штормовой Мыс", "Сердце Земель", "Соколиный Утёс",
    "Янтарная Долина", "Медный Берег", "Пустошь Ветров",
    "Южные Пески", "Виноградные Холмы", "Жемчужная Бухта",
]

# Держава игрока, выбравшего здесь столицу
REALMS = {
    "Северный Предел": "Королевство Северного Предела",
    "Ледяная Гавань": "Княжество Ледяной Гавани",
    "Волчий Перевал": "Орден Волчьего Перевала",
    "Туманные Топи": "Ковен Туманных Топей",
    "Каменный Брод": "Баронство Каменного Брода",
    "Серебряный Кряж": "Королевство Серебряного Кряжа",
    "Штормовой Мыс": "Вольница Штормового Мыса",
    "Сердце Земель": "Империя Сердца Земель",
    "Соколиный Утёс": "Графство Соколиного Утёса",
    "Янтарная Долина": "Королевство Янтарной Долины",
    "Медный Берег": "Республика Медного Берега",
    "Пустошь Ветров": "Каганат Пустоши Ветров",
    "Южные Пески": "Султанат Южных Песков",
    "Виноградные Холмы": "Герцогство Виноградных Холмов",
    "Жемчужная Бухта": "Княжество Жемчужной Бухты",
}

Pt = tuple[float, float]


def sites(rng: random.Random) -> list[Pt]:
    cw, ch = (W - 2 * MARGIN) / COLS, (H - 2 * MARGIN) / ROWS
    out = []
    for r in range(ROWS):
        for c in range(COLS):
            out.append((
                MARGIN + (c + 0.5 + rng.uniform(-0.28, 0.28)) * cw,
                MARGIN + (r + 0.5 + rng.uniform(-0.28, 0.28)) * ch,
            ))
    return out


def clip(poly: list[tuple[Pt, int]], si: Pt, sj: Pt, tag: int) -> list[tuple[Pt, int]]:
    """Сазерленд–Ходжмен по полуплоскости «ближе к si, чем к sj». Вершина несёт тег исходящего ребра."""
    mx, my = (si[0] + sj[0]) / 2, (si[1] + sj[1]) / 2
    nx, ny = sj[0] - si[0], sj[1] - si[1]

    def side(p: Pt) -> float:
        return (p[0] - mx) * nx + (p[1] - my) * ny

    def cross(a: Pt, b: Pt) -> Pt:
        da, db = side(a), side(b)
        t = da / (da - db)
        return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)

    out = []
    for k, (a, t) in enumerate(poly):
        b = poly[(k + 1) % len(poly)][0]
        a_in, b_in = side(a) <= 0, side(b) <= 0
        if a_in:
            out.append((a, t))
            if not b_in:
                out.append((cross(a, b), tag))
        elif b_in:
            out.append((cross(a, b), t))
    return out


def rnd(p: Pt) -> tuple[float, float]:
    return (round(p[0], 1), round(p[1], 1))


def wobble(a: Pt, b: Pt, key: str, depth: int = 3, amp: float = 0.12) -> list[Pt]:
    """Смещение середин: детерминированно по ключу ребра, чтобы у соседей граница совпала."""
    rng = random.Random(key)
    pts = [a, b]
    for d in range(depth):
        nxt = [pts[0]]
        for p, q in zip(pts, pts[1:]):
            dx, dy = q[0] - p[0], q[1] - p[1]
            length = math.hypot(dx, dy)
            off = rng.uniform(-amp, amp) * length
            m = ((p[0] + q[0]) / 2 - dy / length * off, (p[1] + q[1]) / 2 + dx / length * off) if length else p
            nxt += [m, q]
        pts = nxt
    return pts


def edge_points(a: Pt, b: Pt, key: str) -> list[Pt]:
    """Точки ребра a->b (без b). Канонический порядок концов, чтобы оба соседа получили одну линию."""
    ra, rb = rnd(a), rnd(b)
    if ra <= rb:
        pts = wobble(ra, rb, key + str(ra) + str(rb))
    else:
        pts = list(reversed(wobble(rb, ra, key + str(rb) + str(ra))))
    return pts[:-1]


def island(n: int = 40, exp: float = 3.2) -> list[tuple[Pt, int]]:
    """Суперэллипс — выпуклый «остров» со скруглёнными углами; вокруг остаётся море."""
    a, b = W / 2 - 6, H / 2 - 6
    pts = []
    for k in range(n):
        t = 2 * math.pi * k / n
        c, s = math.cos(t), math.sin(t)
        pts.append(((W / 2 + a * math.copysign(abs(c) ** (2 / exp), c),
                     H / 2 + b * math.copysign(abs(s) ** (2 / exp), s)), -1))
    return pts


def build(seed: int) -> dict:
    rng = random.Random(seed)
    ss = sites(rng)
    polys = []
    for i, si in enumerate(ss):
        poly = island()
        for j, sj in enumerate(ss):
            if i != j:
                poly = clip(poly, si, sj, j)
        polys.append(poly)

    shared: dict[tuple[int, int], float] = {}
    for i, poly in enumerate(polys):
        for k, (a, t) in enumerate(poly):
            if t >= 0:
                b = poly[(k + 1) % len(poly)][0]
                key = (min(i, t), max(i, t))
                shared[key] = max(shared.get(key, 0), math.dist(a, b))
    neighbors = {i: set() for i in range(len(ss))}
    for (i, j), length in shared.items():
        if length >= MIN_SHARED_EDGE:
            neighbors[i].add(j)
            neighbors[j].add(i)

    territories = []
    for i, poly in enumerate(polys):
        pts: list[Pt] = []
        for k, (a, t) in enumerate(poly):
            b = poly[(k + 1) % len(poly)][0]
            key = f"{min(i, t)}-{max(i, t)}" if t >= 0 else "coast"
            pts += edge_points(a, b, key)
        d = "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in pts) + " Z"
        # центроид многоугольника — место для подписи и значка столицы
        area = cx = cy = 0.0
        base = [p for p, _ in poly]
        for (x0, y0), (x1, y1) in zip(base, base[1:] + base[:1]):
            f = x0 * y1 - x1 * y0
            area += f
            cx += (x0 + x1) * f
            cy += (y0 + y1) * f
        area /= 2
        territories.append({
            "territory_id": i + 1,
            "name": NAMES[i],
            "base_points": 200,
            "neighbors": sorted(n + 1 for n in neighbors[i]),
            "path": d,
            "cx": round(cx / (6 * area), 1),
            "cy": round(cy / (6 * area), 1),
            "realm": REALMS[NAMES[i]],
        })
    return {"seed": seed, "title": "Остров", "view_box": [0, 0, W, H], "territories": territories}


def check(data: dict) -> list[str]:
    ts = {t["territory_id"]: t for t in data["territories"]}
    problems = []
    degrees = [len(t["neighbors"]) for t in ts.values()]
    if min(degrees) < 2:
        problems.append(f"есть регион с {min(degrees)} соседом")
    if max(degrees) > 6:
        problems.append(f"есть регион с {max(degrees)} соседями")
    seen, stack = set(), [1]
    while stack:
        cur = stack.pop()
        if cur not in seen:
            seen.add(cur)
            stack += ts[cur]["neighbors"]
    if seen != set(ts):
        problems.append("карта несвязна")
    return problems


if __name__ == "__main__":
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 11
    data = build(seed)
    problems = check(data)
    for t in data["territories"]:
        print(t["territory_id"], t["name"], t["neighbors"])
    if problems:
        sys.exit("Плохая карта: " + "; ".join(problems))
    out = Path(__file__).resolve().parent.parent / "app" / "game" / "maps" / "island.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print("->", out)
