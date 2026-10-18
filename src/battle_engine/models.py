from typing import Annotated, Generic, Literal, TypeVar

from annotated_types import Ge, Le
from pydantic import BaseModel, StringConstraints

IDType = TypeVar("IDType", int, str)


class PlayerNameExists(ValueError):
    def __init__(self, name: str) -> None:
        super().__init__(f"Player with name '{name}' exists")


class PlayerBase(BaseModel):
    """Base player model."""

    name: Annotated[str, StringConstraints(max_length=20)]
    description: Annotated[str, StringConstraints(max_length=1000)] = ""
    gold: Annotated[int, Ge(0), Le(1_000_000_000)] = 100
    silver: Annotated[int, Ge(0), Le(1_000_000_000)] = 300
    attack: Annotated[int, Ge(0)] = 70
    defense: Annotated[int, Ge(0)] = 70
    hit_points: Annotated[int, Ge(0)] = 100


class PlayerFull(PlayerBase, Generic[IDType]):
    """Player with persistent ID."""

    id: IDType


class BattleRequest(BaseModel, Generic[IDType]):
    """For submission to battle engine."""

    initiator_id: IDType
    opponent_id: IDType


class BattleRequestReady(BattleRequest):
    """For submission to battle engine. Filled with player data."""

    initiator: PlayerBase
    opponent: PlayerBase


class BattleResultRegular[P](BaseModel):
    """Battle engine output model."""

    type: Literal["regular"] = "regular"
    initiator: P
    opponent: P
    winner: P
    stolen: tuple[int, int]
    report: list[str]


class BattleResultTie[P](BaseModel):
    """Battle engine output model."""

    type: Literal["tie"] = "tie"
    initiator: P
    opponent: P
    report: list[str]


type BattleResult = BattleResultRegular | BattleResultTie


class BattleResultStats(BaseModel):
    result: BattleResult
    num_lock_attempts: int = 1


class LeaderboardEntry(BaseModel):
    """Public API schema."""

    rank: int
    score: int
    player: str
