import asyncio

from alembic import context
from sqlalchemy.engine import Connection

from app.config import get_settings
from app.db import Base, make_engine
import app.models  # noqa: F401 — регистрирует модели в metadata

target_metadata = Base.metadata


def do_run(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_online() -> None:
    engine = make_engine(get_settings().database_url)
    async with engine.connect() as conn:
        await conn.run_sync(do_run)
    await engine.dispose()


if context.is_offline_mode():
    context.configure(url=get_settings().database_url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    asyncio.run(run_online())
