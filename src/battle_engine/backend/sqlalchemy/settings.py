from ...settings import SettingsBase


class Settings(SettingsBase):
    DB_URL: str = "sqlite+aiosqlite:///db.sqlite3"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)


settings = Settings()
