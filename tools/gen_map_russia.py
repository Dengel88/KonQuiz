"""Генератор карты России: 15 игровых регионов, собранных из субъектов РФ.

Источник — Natural Earth, admin-1 1:50m (public domain). Файл скачивается один раз в
tools/.cache/. Субъекты объединяются по таблице GROUPS, проецируются в равновеликую
коническую Альберса (стандарт для карт России) и затем проходят «лупу» (fisheye) с центром
около Москвы: европейская часть на экране телефона иначе получается слишком мелкой, чтобы в
неё попадать пальцем. Лупа непрерывная, поэтому соседство и силуэт страны сохраняются.

Соседство — из геометрии (общая граница длиннее MIN_SHARED), как в gen_map.py: игрок видит
ровно те связи, по которым сервер разрешает атаки. Острова (Сахалин и т.п.) и эксклав
(Калининград) входят в свой регион и на соседство не влияют.

Нужен shapely (requirements-dev.txt). Запуск:
  python tools/gen_map_russia.py  ->  app/game/maps/russia.json
"""

import json
import math
import sys
import urllib.request
from pathlib import Path

from shapely import affinity
from shapely.geometry import MultiPolygon, Polygon, shape
from shapely.ops import polylabel, transform, unary_union

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "tools" / ".cache" / "ne_50m_admin_1_states_provinces.geojson"
SOURCE_URL = (
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/"
    "geojson/ne_50m_admin_1_states_provinces.geojson"
)
OUT = ROOT / "app" / "game" / "maps" / "russia.json"

WIDTH = 1000  # ширина viewBox; высота — по пропорциям
MARGIN = 16
SIMPLIFY = 1.1  # допуск упрощения контуров, в единицах viewBox
MIN_PART_AREA = 18.0  # мелкие острова (в ед.² viewBox) выкидываем — на телефоне это пиксель
MIN_SHARED = 6.0  # общая граница короче — касание углом, не соседство

# Коды ISO 3166-2 субъектов. Ключ — (id, название). Порядок id: примерно с запада на восток.
GROUPS: dict[tuple[int, str], list[str]] = {
    (1, "Северо-Запад"): ["RU-KGD", "RU-LEN", "RU-SPE", "RU-PSK", "RU-NGR", "RU-KR", "RU-MUR"],
    (2, "Русский Север"): ["RU-ARK", "RU-NEN", "RU-KO", "RU-VLG"],
    (3, "Москва"): ["RU-MOW", "RU-MOS", "RU-TVE", "RU-YAR", "RU-VLA", "RU-IVA", "RU-KOS",
                    "RU-RYA", "RU-TUL", "RU-KLU", "RU-SMO"],
    (4, "Черноземье"): ["RU-BRY", "RU-ORL", "RU-KRS", "RU-BEL", "RU-VOR", "RU-LIP", "RU-TAM"],
    (5, "Юг"): ["RU-ROS", "RU-KDA", "RU-AD", "UA-43", "UA-40"],
    # Калмыкия и Астрахань здесь, Волгоград — в Поволжье: иначе у Кавказа единственный сосед
    (6, "Кавказ"): ["RU-STA", "RU-DA", "RU-CE", "RU-IN", "RU-SE", "RU-KB", "RU-KC", "RU-KL", "RU-AST"],
    (7, "Поволжье"): ["RU-NIZ", "RU-MO", "RU-CU", "RU-ME", "RU-TA", "RU-ULY", "RU-PNZ",
                      "RU-SAM", "RU-SAR", "RU-VGG"],
    (8, "Урал"): ["RU-KIR", "RU-UD", "RU-PER", "RU-BA", "RU-ORE", "RU-SVE", "RU-CHE", "RU-KGN"],
    (9, "Югра и Ямал"): ["RU-TYU", "RU-KHM", "RU-YAN"],
    (10, "Сибирь"): ["RU-OMS", "RU-NVS", "RU-TOM", "RU-KEM", "RU-ALT", "RU-AL"],
    (11, "Енисей"): ["RU-KYA", "RU-KK", "RU-TY"],
    (12, "Байкал"): ["RU-IRK", "RU-BU", "RU-ZAB"],
    (13, "Якутия"): ["RU-SA"],
    (14, "Приамурье"): ["RU-AMU", "RU-KHA", "RU-PRI", "RU-YEV", "RU-SAK"],
    (15, "Камчатка и Чукотка"): ["RU-KAM", "RU-MAG", "RU-CHU"],
}

# Держава игрока, выбравшего здесь столицу. Исторические княжества были только в европейской
# части, поэтому на востоке — «земли» и ханство той же эпохи.
REALMS = {
    1: "Новгородская земля",
    2: "Двинская земля",
    3: "Московское княжество",
    4: "Курское княжество",
    5: "Тмутараканское княжество",
    6: "Алания",
    7: "Нижегородское княжество",
    8: "Великая Пермь",
    9: "Югорская земля",
    10: "Сибирское ханство",
    11: "Енисейская земля",
    12: "Даурия",
    13: "Якутская земля",
    14: "Приамурская земля",
    15: "Камчатская земля",
}

# Альберс: центральный меридиан и стандартные параллели — как на типовых картах России
LON0, LAT1, LAT2, LAT0 = 100.0, 52.0, 64.0, 60.0
# Лупа (Саркар–Браун): центр, радиус (в км) и сила увеличения (в центре — в 1+M раз)
FISH_LON, FISH_LAT, FISH_R, FISH_M = 46.0, 54.0, 4600.0, 1.9


def albers(lon: float, lat: float) -> tuple[float, float]:
    """Проекция в км. Долготы Чукотки за 180° переносим (lon<0 → +360), иначе она «уедет» на запад."""
    if lon < 0:
        lon += 360
    r = 6371.0
    f1, f2, f0 = (math.radians(v) for v in (LAT1, LAT2, LAT0))
    n = (math.sin(f1) + math.sin(f2)) / 2
    c = math.cos(f1) ** 2 + 2 * n * math.sin(f1)
    rho0 = r * math.sqrt(c - 2 * n * math.sin(f0)) / n
    rho = r * math.sqrt(c - 2 * n * math.sin(math.radians(lat))) / n
    theta = n * math.radians(lon - LON0)
    return rho * math.sin(theta), rho0 - rho * math.cos(theta)  # y вверх (как у широты)


FX, FY = albers(FISH_LON, FISH_LAT)


def fisheye(x: float, y: float) -> tuple[float, float]:
    dx, dy = x - FX, y - FY
    d = math.hypot(dx, dy)
    if d == 0 or d >= FISH_R:
        return x, y
    t = d / FISH_R
    k = FISH_R * (FISH_M + 1) * t / (FISH_M * t + 1) / d
    return FX + dx * k, FY + dy * k


def project(geom):
    def fn(xs, ys, zs=None):
        pts = [fisheye(*albers(x, y)) for x, y in zip(xs, ys)]
        return [p[0] for p in pts], [p[1] for p in pts]

    return transform(fn, densify(geom))


def densify(geom, step: float = 0.5):
    """Вставить точки через step градусов: после лупы и конической проекции прямые рёбра гнутся."""
    return geom.segmentize(step)


def load_subjects() -> dict[str, object]:
    if not CACHE.exists():
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        print("Скачиваю", SOURCE_URL)
        urllib.request.urlretrieve(SOURCE_URL, CACHE)
    raw = json.loads(CACHE.read_text(encoding="utf-8"))
    return {
        f["properties"]["iso_3166_2"]: shape(f["geometry"])
        for f in raw["features"]
        if f["properties"].get("adm0_a3") == "RUS"
    }


def parts(geom) -> list[Polygon]:
    return list(geom.geoms) if isinstance(geom, MultiPolygon) else [geom]


def svg_path(geom) -> str:
    out = []
    for poly in parts(geom):
        for ring in (poly.exterior, *poly.interiors):
            pts = list(ring.coords)[:-1]
            out.append("M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in pts) + " Z")
    return " ".join(out)


def build() -> dict:
    subjects = load_subjects()
    used = [code for codes in GROUPS.values() for code in codes]
    missing = sorted(set(used) - set(subjects))
    unused = sorted(set(subjects) - set(used))
    if missing or unused:
        sys.exit(f"Таблица GROUPS не сходится с данными: нет в данных {missing}, не распределены {unused}")

    # 1) объединяем субъекты; небольшой buffer склеивает щели между полигонами источника
    regions = {}
    for (tid, name), codes in GROUPS.items():
        geom = unary_union([project(subjects[c]).buffer(0.5) for c in codes]).buffer(-0.5)
        regions[tid] = (name, geom)

    # 2) в единицы viewBox: y вниз, ширина WIDTH
    minx, miny, maxx, maxy = unary_union([g for _, g in regions.values()]).bounds
    scale = (WIDTH - 2 * MARGIN) / (maxx - minx)
    height = round((maxy - miny) * scale + 2 * MARGIN)

    def to_view(g):
        g = affinity.translate(g, -minx, -maxy)
        g = affinity.scale(g, scale, -scale, origin=(0, 0))
        return affinity.translate(g, MARGIN, MARGIN)

    regions = {tid: (name, to_view(g)) for tid, (name, g) in regions.items()}

    # 3) соседство — до упрощения, по длине общей границы
    neighbors: dict[int, list[int]] = {tid: [] for tid in regions}
    ids = sorted(regions)
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            shared = regions[a][1].buffer(1.0).intersection(regions[b][1].buffer(1.0))
            # полоса вдоль общей границы шириной ~2 → её длина ≈ площадь / 2
            if shared.area / 2 >= MIN_SHARED:
                neighbors[a].append(b)
                neighbors[b].append(a)

    # 4) упрощение (с сохранением топологии общих границ — через общий union по рёбрам не
    #    заморачиваемся: допуск ~1 ед. на экране неразличим) и отсев крошечных островов
    territories = []
    for tid in ids:
        name, geom = regions[tid]
        kept = [p for p in parts(geom.simplify(SIMPLIFY, preserve_topology=True)) if p.area >= MIN_PART_AREA]
        geom = MultiPolygon(kept) if len(kept) > 1 else kept[0]
        main = max(parts(geom), key=lambda p: p.area)
        label = polylabel(main, tolerance=1.0)
        territories.append({
            "territory_id": tid, "name": name, "base_points": 200,
            "neighbors": sorted(neighbors[tid]), "path": svg_path(geom),
            "cx": round(label.x, 1), "cy": round(label.y, 1), "realm": REALMS[tid],
        })

    outline = unary_union([g for _, g in regions.values()]).buffer(0.8).buffer(-0.8)
    outline = MultiPolygon([p for p in parts(outline.simplify(SIMPLIFY)) if p.area >= MIN_PART_AREA])
    return {
        "title": "Россия",
        "view_box": [0, 0, WIDTH, height],
        "outline": svg_path(outline),  # силуэт страны — для свечения/фаски «слитка» на клиенте
        "territories": territories,
    }


def check(data: dict) -> list[str]:
    ts = {t["territory_id"]: t for t in data["territories"]}
    problems = [f"{t['name']}: нет соседей" for t in ts.values() if not t["neighbors"]]
    seen, stack = set(), [1]
    while stack:
        cur = stack.pop()
        if cur not in seen:
            seen.add(cur)
            stack.extend(ts[cur]["neighbors"])
    if seen != set(ts):
        problems.append(f"граф несвязный: недостижимы {sorted(set(ts) - seen)}")
    return problems


if __name__ == "__main__":
    data = build()
    for t in data["territories"]:
        print(t["territory_id"], t["name"], t["neighbors"], (t["cx"], t["cy"]))
    problems = check(data)
    if problems:
        sys.exit("Плохая карта: " + "; ".join(problems))
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print("->", OUT, "viewBox", data["view_box"], f"{OUT.stat().st_size // 1024} КБ")
