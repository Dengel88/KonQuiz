import fakeredis
import pytest

from app.config import Settings
from app.db import Base, make_engine, make_sessionmaker
from app.game.services import Economy, EngineDeps, MatchStore, QuestionRepo
from app.seed import seed_questions

FAST = dict(
    matchmaking_timeout=0.05, exact_question_time=0.3, choice_question_time=0.3, pick_time=0.15,
    attack_choice_time=0.15, reveal_time=0.0, realm_reveal_time=0.0, bot_delay_min=0.01, bot_delay_max=0.04,
    bot_pick_delay_min=0.01, bot_pick_delay_max=0.02,
)


@pytest.fixture
async def sm(tmp_path):
    engine = make_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = make_sessionmaker(engine)
    await seed_questions(maker)
    yield maker
    await engine.dispose()


def make_deps(sm, **overrides) -> EngineDeps:
    settings = Settings(_env_file=None, **{**FAST, **overrides})
    return EngineDeps(
        settings=settings,
        questions=QuestionRepo(sm),
        economy=Economy(sm),
        store=MatchStore(fakeredis.aioredis.FakeRedis(), ttl=60),
    )


@pytest.fixture
def deps(sm) -> EngineDeps:
    return make_deps(sm)
