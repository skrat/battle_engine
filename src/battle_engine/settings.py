import os

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()

SETTINGS_MODULE = os.getenv("SETTINGS_MODULE", "battle_engine.backend.redis.settings")


class SettingsBase(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
        env_ignore_empty=True,
    )

    BACKEND: str = "battle_engine.backend.redis.impl:RedisBackend"

    API_KEY_HEADER: str
    API_KEY_SECRET: str

    STAT_HEADER: str = "X-Battle-Lock-Stat"
    STAT_HEADER_FLAG: bool = True

    BATTLE_LOCK_TTL: int = 2
    BATTLE_LOCK_POLL_INTERVAL: float = 0.002
    BATTLE_LOCK_MAX_POLL: float = 2

    WITH_TASKIQ: bool = False

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        for field_name in self.__class__.model_fields:
            value = getattr(self, field_name)
            if (
                isinstance(value, str)
                and len(value) >= 2
                and (
                    (value.startswith('"') and value.endswith('"'))
                    or (value.startswith("'") and value.endswith("'"))
                )
            ):
                setattr(self, field_name, value[1:-1])


settings = SettingsBase()
