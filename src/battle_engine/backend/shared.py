import importlib
from collections.abc import Awaitable
from contextlib import asynccontextmanager
from typing import Generic, Protocol, TypeVar, runtime_checkable

from ..models import (
    BattleRequest,
    BattleResultStats,
    LeaderboardEntry,
    PlayerBase,
    PlayerFull,
)
from ..settings import settings

PlayerModel_co = TypeVar(
    "PlayerModel_co",
    bound=PlayerFull,
    covariant=True,
)


@runtime_checkable
class Backend(Protocol, Generic[PlayerModel_co]):
    @asynccontextmanager
    async def lifespan(self):
        """FastAPI lifespan hook."""
        yield

    async def create_player(self, p: PlayerBase) -> PlayerModel_co:
        """Create and persist a player."""
        ...

    async def resolve_battle(
        self, req: BattleRequest, _wait_for: Awaitable[None] | None = None
    ) -> BattleResultStats:
        """Wait for battle players to become available (until all battles they are in are
        finished), then processes the battle and returns the outcome."""
        ...

    async def leaderboard(self, limit: int = 100) -> list[LeaderboardEntry]:
        """Retrieve leaderboard."""
        ...


def get_backend_impl():
    """Create backend instance."""
    try:
        backend_mod_name, backend_cls_name = settings.BACKEND.split(":")
        backend_mod = importlib.import_module(backend_mod_name)
        backend_cls = getattr(backend_mod, backend_cls_name)
        backend = backend_cls()
        assert isinstance(backend, Backend), "backend protocol"
        return backend
    except Exception as e:
        raise RuntimeError("Failed to set backend") from e
