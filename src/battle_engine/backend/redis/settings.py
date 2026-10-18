from ...settings import SettingsBase


class Settings(SettingsBase):
    REDIS_URL: str
    REDIS_MAX_CONNECTIONS: int = 750
    REDIS_TIMEOUT: int = 30
    REDIS_SOCKET_TIMEOUT: int | None = None

    BATTLE_LOCK_TTL: int = 2
    BATTLE_LOCK_POLL_INTERVAL: float = 0.002
    BATTLE_LOCK_MAX_POLL: float = 2

    def __init__(self, **kwargs):
        super().__init__(**kwargs)


settings = Settings()
