"""Проверка Telegram Mini App initData.

Алгоритм из документации Telegram (core.telegram.org/bots/webapps):
secret = HMAC_SHA256(key="WebAppData", msg=bot_token);
hash   = HMAC_SHA256(key=secret, msg="k=v\\n..." по всем полям кроме hash, сортировка по ключу).

DEV_AUTH_BYPASS=true дополнительно принимает строку "dev:<id>:<username>" — только для локальной разработки.
"""

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from urllib.parse import parse_qsl

from app.config import Settings


class AuthError(Exception):
    pass


@dataclass(frozen=True)
class TgUser:
    id: int
    username: str


def validate_init_data(init_data: str, bot_token: str, max_age: int, now: float | None = None) -> TgUser:
    if not bot_token:
        raise AuthError("BOT_TOKEN не задан")
    pairs = dict(parse_qsl(init_data, keep_blank_values=True, strict_parsing=False))
    received = pairs.pop("hash", None)
    if not received:
        raise AuthError("Нет hash")
    check_string = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received):
        raise AuthError("Неверная подпись initData")
    try:
        auth_date = int(pairs.get("auth_date", "0"))
    except ValueError:
        raise AuthError("Некорректный auth_date") from None
    if (now or time.time()) - auth_date > max_age:
        raise AuthError("initData устарела")
    try:
        user = json.loads(pairs["user"])
        return TgUser(id=int(user["id"]), username=user.get("username") or user.get("first_name") or "")
    except (KeyError, ValueError, TypeError):
        raise AuthError("Нет данных пользователя") from None


def authenticate(init_data: str, settings: Settings) -> TgUser:
    if settings.dev_auth_bypass and init_data.startswith("dev:"):
        parts = init_data.split(":", 2)
        try:
            return TgUser(id=int(parts[1]), username=parts[2] if len(parts) > 2 else f"dev{parts[1]}")
        except (IndexError, ValueError):
            raise AuthError("Формат: dev:<id>:<username>") from None
    return validate_init_data(init_data, settings.bot_token, settings.init_data_max_age)
