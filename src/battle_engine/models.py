from enum import IntEnum
from typing import Annotated, Any, Generic, Literal, TypeVar

from annotated_types import Ge, Le
from pydantic import BaseModel, StringConstraints, model_validator

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


P = TypeVar("P", bound=PlayerBase)


class PlayerFull(PlayerBase, Generic[IDType]):
    """Player with persistent ID."""

    id: IDType


class BattleRequest(BaseModel, Generic[IDType]):
    """For submission to battle engine."""

    initiator_id: IDType
    opponent_id: IDType

    @model_validator(mode="before")
    @classmethod
    def check_self_battle(cls, data: Any) -> Any:
        if str(data["initiator_id"]) == str(data["opponent_id"]):
            raise ValueError("self-battle now allowed")
        return data


class BattleRequestReady(BattleRequest):
    """For submission to battle engine. Filled with player data."""

    initiator: PlayerBase
    opponent: PlayerBase


class BattleTurnResult(IntEnum):
    HIT = 1
    MISS = 2


class BattleTurnHit(BaseModel, Generic[P]):
    """One turn in the battle."""

    type: Literal[BattleTurnResult.HIT] = BattleTurnResult.HIT
    attacking_player: P
    defending_player: P
    damange: int

    def __str__(self) -> str:
        return f" ! {self.attacking_player.name} hit {self.defending_player.name} with {self.damange} damange!"


class BattleTurnMiss(BaseModel, Generic[P]):
    """One turn in the battle."""

    type: Literal[BattleTurnResult.MISS] = BattleTurnResult.MISS
    attacking_player: P
    defending_player: P

    def __str__(self) -> str:
        return f" % {self.attacking_player.name} missed."


type BattleTurn = BattleTurnHit | BattleTurnMiss

type BattleReport = list[BattleTurn]


class BattleResultRegular(BaseModel, Generic[P]):
    """Battle engine output model."""

    type: Literal["regular"] = "regular"
    initiator: P
    opponent: P
    winner: P
    stolen: tuple[int, int]
    report: BattleReport


class BattleResultTie(BaseModel, Generic[P]):
    """Battle engine output model."""

    type: Literal["tie"] = "tie"
    initiator: P
    opponent: P
    report: BattleReport


type BattleResult = BattleResultRegular | BattleResultTie


class BattleResultStats(BaseModel):
    result: BattleResult
    num_lock_attempts: int = 1


class LeaderboardEntry(BaseModel):
    """Public API schema."""

    rank: int
    score: int
    player: str
