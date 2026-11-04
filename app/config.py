from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Все настройки — из переменных окружения / .env. Секреты в коде не хардкодим."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://konquiz:konquiz@localhost:5432/konquiz"
    redis_url: str = "redis://localhost:6379/0"  # "memory://" — fakeredis, для запуска без Redis
    # Для локального запуска без Alembic: создать таблицы и залить вопросы, если база пустая
    auto_create_tables: bool = False
    auto_seed: bool = False

    # Telegram
    bot_token: str = ""
    init_data_max_age: int = 24 * 3600  # сек; старше — отклоняем
    dev_auth_bypass: bool = False  # принимает init_data вида "dev:<id>:<username>"
    enable_test_endpoints: bool = False

    # Тайминги FSM (сек)
    matchmaking_timeout: float = 15.0
    exact_question_time: float = 15.0
    choice_question_time: float = 10.0
    pick_time: float = 10.0
    attack_choice_time: float = 20.0
    reveal_time: float = 3.0  # пауза «показать результат» — под анимации на клиенте
    realm_reveal_time: float = 8.0  # пауза после выбора столицы — ролик «держава основана»
    freeze_bonus: float = 10.0

    # Боты
    bot_delay_min: float = 3.0
    bot_delay_max: float = 8.0
    bot_pick_delay_min: float = 1.0
    bot_pick_delay_max: float = 3.0

    # Правила
    players_per_match: int = 3
    battle_rounds: int = 5
    capital_bonus: int = 400
    match_state_ttl: int = 3600  # сколько держать MatchState в Redis


@lru_cache
def get_settings() -> Settings:
    return Settings()
