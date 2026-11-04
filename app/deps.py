"""FastAPI-зависимости. HTTPConnection работает и для HTTP, и для WebSocket."""

from fastapi import Depends, Header, HTTPException
from starlette.requests import HTTPConnection

from app.auth import AuthError, TgUser, authenticate
from app.config import Settings
from app.game.manager import MatchManager
from app.game.services import Economy, MatchStore
from app.ws.connections import ConnectionManager


def get_settings_dep(conn: HTTPConnection) -> Settings:
    return conn.app.state.settings


def get_manager(conn: HTTPConnection) -> MatchManager:
    return conn.app.state.manager


def get_connections(conn: HTTPConnection) -> ConnectionManager:
    return conn.app.state.connections


def get_economy(conn: HTTPConnection) -> Economy:
    return conn.app.state.economy


def get_store(conn: HTTPConnection) -> MatchStore:
    return conn.app.state.store


async def current_user(
    x_init_data: str = Header(..., description="Telegram WebApp initData"),
    settings: Settings = Depends(get_settings_dep),
    economy: Economy = Depends(get_economy),
) -> TgUser:
    try:
        user = authenticate(x_init_data, settings)
    except AuthError as err:
        raise HTTPException(status_code=401, detail=str(err)) from None
    await economy.upsert_user(user.id, user.username)
    return user
