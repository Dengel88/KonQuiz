"""Карты — по JSON-файлу на карту в app/game/maps/ (генерируют tools/gen_map.py и gen_map_russia.py).

Один файл и для сервера (соседство), и для клиента (контуры регионов): соседство вычислено
из геометрии, так что на экране видны ровно те границы, по которым разрешены атаки.
Id карты = имя файла без .json. Порядок в MAPS: сначала DEFAULT_MAP, остальные по алфавиту.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

MAPS_DIR = Path(__file__).with_name("maps")
DEFAULT_MAP = "russia"


@dataclass(frozen=True)
class Territory:
    territory_id: int
    name: str
    base_points: int
    neighbors: tuple[int, ...]
    path: str  # SVG path в координатах view_box
    cx: float  # точка для подписи/значка
    cy: float
    realm: str = ""  # держава игрока, чья столица здесь: «Московское княжество»


@dataclass(frozen=True)
class GameMap:
    id: str
    title: str
    view_box: list[float]
    territories: dict[int, Territory]
    extra: dict = field(default_factory=dict)  # декоративные слои для клиента (контур, подписи морей…)

    def neighbors(self, tid: int) -> tuple[int, ...]:
        return self.territories[tid].neighbors

    def public(self) -> dict:
        return {
            "id": self.id, "title": self.title, "view_box": self.view_box,
            "territories": [
                {"territory_id": t.territory_id, "name": t.name, "base_points": t.base_points,
                 "neighbors": list(t.neighbors), "path": t.path, "cx": t.cx, "cy": t.cy,
                 "realm": t.realm}
                for t in self.territories.values()
            ],
            **self.extra,
        }


def _load(path: Path) -> GameMap:
    raw = json.loads(path.read_text(encoding="utf-8"))
    territories = {
        t["territory_id"]: Territory(
            territory_id=t["territory_id"], name=t["name"], base_points=t["base_points"],
            neighbors=tuple(t["neighbors"]), path=t["path"], cx=t["cx"], cy=t["cy"],
            realm=t.get("realm", ""),
        )
        for t in raw["territories"]
    }
    known = {"seed", "title", "view_box", "territories"}
    return GameMap(
        id=path.stem, title=raw.get("title", path.stem), view_box=raw["view_box"],
        territories=territories, extra={k: v for k, v in raw.items() if k not in known},
    )


def _load_all() -> dict[str, GameMap]:
    maps = {m.id: m for m in map(_load, sorted(MAPS_DIR.glob("*.json")))}
    ordered = sorted(maps, key=lambda mid: (mid != DEFAULT_MAP, mid))
    return {mid: maps[mid] for mid in ordered}


MAPS = _load_all()


def resolve(map_id: str | None) -> GameMap:
    """Неизвестный id — карта по умолчанию (как и с темами: клиент не может сломать матч)."""
    if map_id in MAPS:
        return MAPS[map_id]
    return MAPS.get(DEFAULT_MAP) or next(iter(MAPS.values()))
