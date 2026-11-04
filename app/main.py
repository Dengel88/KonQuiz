import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from redis.asyncio import Redis

from app.api import router, test_router
from app.config import Settings, get_settings
from app.db import Base, make_engine, make_sessionmaker
from app.game.manager import MatchManager
from app.game.services import Economy, EngineDeps, MatchStore, QuestionRepo
from app.seed import seed_questions
from app.ws.connections import ConnectionManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
STATIC_DIR = Path(__file__).parent / "static"


def make_redis(url: str) -> Redis:
    if url.startswith("memory://"):
        import fakeredis  # dev-зависимость: локальный запуск без Redis

        return fakeredis.aioredis.FakeRedis()
    return Redis.from_url(url)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        db = make_engine(settings.database_url)
        if settings.auto_create_tables:
            async with db.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
        sm = make_sessionmaker(db)
        if settings.auto_seed:
            await seed_questions(sm)
        redis = make_redis(settings.redis_url)

        economy = Economy(sm)
        store = MatchStore(redis, settings.match_state_ttl)
        deps = EngineDeps(settings=settings, questions=QuestionRepo(sm), economy=economy, store=store)
        app.state.settings = settings
        app.state.economy = economy
        app.state.store = store
        app.state.manager = MatchManager(deps)
        app.state.connections = ConnectionManager()
        logging.getLogger("konquiz").info("KonQuiz backend запущен")
        yield
        await app.state.manager.shutdown()
        await redis.aclose()
        await db.dispose()

    app = FastAPI(title="KonQuiz", lifespan=lifespan)
    app.include_router(router)
    if settings.enable_test_endpoints:
        app.include_router(test_router)
    app.mount("/demo", StaticFiles(directory=STATIC_DIR, html=True), name="demo")
    # Сам Mini App — в корне; монтируем последним, чтобы не перекрыть /api и /ws
    app.mount("/", StaticFiles(directory=STATIC_DIR / "game", html=True), name="game")
    return app


app = create_app()
