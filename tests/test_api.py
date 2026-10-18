import asyncio
import random
from typing import IO, Any

from httpx2 import AsyncClient, Response

from battle_engine.models import PlayerBase, PlayerFull
from battle_engine.settings import settings

# === Player tests


async def test_create_player(client: AsyncClient):
    resp = await client.post("/player", json={"name": "one"})
    data = resp.json()
    assert resp.status_code == 200
    assert data["name"] == "one"
    assert data["id"] is not None


async def test_create_player_fails_unique(client: AsyncClient):
    resp1 = await client.post("/player", json={"name": "one"})
    resp2 = await client.post("/player", json={"name": "one"})
    assert resp1.status_code == 200
    assert resp2.status_code == 422
    assert resp2.json() == {"detail": ["name"]}

    resps = await asyncio.gather(
        client.post("/player", json={"name": "two"}),
        client.post("/player", json={"name": "two"}),
    )
    srt = sorted(resps, key=lambda r: r.status_code)
    assert srt[0].status_code == 200
    assert srt[1].status_code == 422


async def test_create_player_fails_schema(client: AsyncClient):
    resp1 = await client.post("/player", json={"one": "name"})
    assert resp1.status_code == 422


# === Battle tests


def cnt():
    cnt = 0
    while True:
        cnt += 1
        yield cnt


async def make_player(client: AsyncClient, i: int, data: dict):
    n = random.choice(["Jane", "Joe", "Joseph"])
    resp = await client.post("/player", json={"name": f"{n}{i}", **data})
    assert resp.status_code == 200
    return PlayerFull(**resp.json())


async def post_player(client: AsyncClient, p: PlayerBase):
    return PlayerFull(
        **(
            await client.post(
                "/player",
                json=p.model_dump(),
            )
        ).json(),
    )


async def test_create_battle(client: AsyncClient):
    counter = cnt()
    p1 = await make_player(client, next(counter), {})
    p2 = await make_player(client, next(counter), {"defense": 20})
    resp = await client.post(f"/battle/{p1.id}/{p2.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["winner"]["name"] == p1.name


async def test_battle_lock_stat_present(client: AsyncClient):
    counter = cnt()
    p1 = await make_player(client, next(counter), {})
    p2 = await make_player(client, next(counter), {"defense": 20})
    resp = await client.post(f"/battle/{p1.id}/{p2.id}")
    assert resp.status_code == 200
    assert resp.headers[settings.STAT_HEADER] is not None


async def test_create_battle_fails_nonexist_player(client: AsyncClient):
    resp = await client.post("/battle/12/999")
    assert resp.status_code == 404


async def test_victory(client: AsyncClient):
    counter = cnt()
    p1 = await make_player(client, next(counter), {"attack": 70, "defense": 50})
    p2 = await make_player(client, next(counter), {"attack": 50, "defense": 30})
    resp = await client.post(f"/battle/{p1.id}/{p2.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["winner"]["name"] == p1.name

    p1 = await make_player(client, next(counter), {"attack": 20, "defense": 20})
    p2 = await make_player(client, next(counter), {"attack": 50, "defense": 30})
    resp = await client.post(f"/battle/{p1.id}/{p2.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["winner"]["name"] == p2.name


async def test_concurrent(client: AsyncClient):
    p100 = await post_player(client, PlayerBase(name="p100", attack=100, defense=100))
    p1 = await post_player(client, PlayerBase(name="p1", attack=50, defense=60))
    p2 = await post_player(client, PlayerBase(name="p2", attack=70, defense=80))
    battles = [
        # initiator, opponent, expected winner
        (p1, p2, p2),
        (p1, p100, p100),
        (p2, p100, p100),
    ]

    # Submit battles
    btasks: list[asyncio.Task[Response]] = []
    for p1, p2, _ in battles:
        await asyncio.sleep(1 / 1000)
        btasks.append(asyncio.create_task(client.post(f"/battle/{p1.id}/{p2.id}")))

    bresps = await asyncio.gather(*btasks)
    for i in range(len(battles)):
        assert bresps[i].json()["winner"]["name"] == battles[i][2].name


async def test_leaderboard(client: AsyncClient, battle_path="/battle"):
    counter = cnt()
    p1 = await make_player(client, next(counter), {"attack": 80, "defense": 60})
    p2 = await make_player(client, next(counter), {"attack": 60, "defense": 30})
    p3 = await make_player(client, next(counter), {"attack": 40, "defense": 20})
    p4 = await make_player(client, next(counter), {"attack": 80, "defense": 70})

    resp = await client.post(f"{battle_path}/{p1.id}/{p2.id}")
    assert resp.status_code == 200

    resp = await client.get("/leaderboard")
    assert resp.status_code == 200
    data = resp.json()

    assert len(data) == 1
    assert data[0]["player"] == p1.id

    await client.post(f"{battle_path}/{p3.id}/{p1.id}")
    await client.post(f"{battle_path}/{p4.id}/{p1.id}")
    await client.post(f"{battle_path}/{p3.id}/{p4.id}")

    resp = await client.get("/leaderboard")
    assert resp.status_code == 200
    data = resp.json()

    assert len(data) == 2
    assert data[0]["score"] >= data[1]["score"], "entries are sorted"


async def test_security(client: AsyncClient):
    h = client.headers
    client.headers = {}
    resp = await client.post("/player", json={"name": "joe"})
    assert resp.status_code == 401
    client.headers = h


def wait_for_string(stream: IO[Any], pattern: str):
    for line in iter(stream.readline, b""):
        if pattern in line:
            break


async def test_defer(client, worker):
    await test_leaderboard(client, "/battle_defer")
