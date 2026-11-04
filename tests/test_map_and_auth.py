import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest

from app.auth import AuthError, authenticate, validate_init_data
from app.config import Settings
from app.game.map_topology import DEFAULT_MAP, MAPS, resolve


def test_maps_registry():
    assert DEFAULT_MAP in MAPS and "island" in MAPS
    assert next(iter(MAPS)) == DEFAULT_MAP
    assert resolve("nonsense").id == DEFAULT_MAP


@pytest.mark.parametrize("map_id", list(MAPS))
def test_map_symmetric_and_connected(map_id):
    MAP = MAPS[map_id].territories
    assert len(MAP) == 15
    assert all(t.base_points > 0 and t.path and t.realm for t in MAP.values())
    assert len({t.realm for t in MAP.values()}) == len(MAP)  # у каждой столицы своя держава
    for tid, t in MAP.items():
        for n in t.neighbors:
            assert tid in MAP[n].neighbors, f"{tid}->{n} без обратного ребра"
    seen, stack = set(), [1]
    while stack:
        cur = stack.pop()
        if cur not in seen:
            seen.add(cur)
            stack.extend(MAP[cur].neighbors)
    assert seen == set(MAP)


TOKEN = "123456:TEST-TOKEN"


def sign(fields: dict[str, str], token: str = TOKEN) -> str:
    check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    return urlencode({**fields, "hash": hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()})


def fields(auth_date: int) -> dict[str, str]:
    return {
        "auth_date": str(auth_date),
        "query_id": "AAH",
        "user": json.dumps({"id": 42, "first_name": "Ярик", "username": "dengel"}, ensure_ascii=False),
    }


def test_init_data_valid():
    user = validate_init_data(sign(fields(int(time.time()))), TOKEN, max_age=3600)
    assert (user.id, user.username) == (42, "dengel")


def test_init_data_tampered_and_expired():
    good = sign(fields(int(time.time())))
    with pytest.raises(AuthError):
        validate_init_data(good.replace("dengel", "hacker"), TOKEN, max_age=3600)
    with pytest.raises(AuthError):
        validate_init_data(good, "other:token", max_age=3600)
    with pytest.raises(AuthError):
        validate_init_data(sign(fields(int(time.time()) - 7200)), TOKEN, max_age=3600)


def test_dev_bypass_only_when_enabled():
    on = Settings(_env_file=None, dev_auth_bypass=True, bot_token=TOKEN)
    assert authenticate("dev:7:tester", on).id == 7
    off = Settings(_env_file=None, dev_auth_bypass=False, bot_token=TOKEN)
    with pytest.raises(AuthError):
        authenticate("dev:7:tester", off)
