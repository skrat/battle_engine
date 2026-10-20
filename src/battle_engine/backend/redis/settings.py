from ...settings import SettingsBase


class Settings(SettingsBase):
    REDIS_URL: str
    REDIS_MAX_CONNECTIONS: int = 750
    REDIS_TIMEOUT: int = 30
    REDIS_SOCKET_TIMEOUT: int | None = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)


settings = Settings()
