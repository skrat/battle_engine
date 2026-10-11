import asyncio
import itertools
import os
import random
from time import sleep
from typing import IO, Any, Coroutine

import httpx2
from fastapi.testclient import TestClient
from httpx2 import AsyncClient, Response
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from battle_engine.models import Player
from battle_engine.settings import settings
from tests.util import subprocess_wait_for

# === Player tests


def test_create_player(client: TestClient):
    resp = client.post("/player", json={"name": "one"})
    data = resp.json()
    assert resp.status_code == 200
    assert data["name"] == "one"
    assert data["id"] is not None


def test_create_player_fails_unique(client: TestClient):
    resp1 = client.post("/player", json={"name": "one"})
    resp2 = client.post("/player", json={"name": "one"})
    assert resp1.status_code == 200
    assert resp2.status_code == 422
    assert resp2.json() == {"detail": ["name"]}


def test_create_player_fails_schema(client: TestClient):
    resp1 = client.post("/player", json={"one": "name"})
    assert resp1.status_code == 422


# === Battle tests


def cnt():
    cnt = 0
    while True:
        cnt += 1
        yield cnt


def make_player(client: TestClient | httpx2.Client, i: int, data: dict):
    n = random.choice(["Jane", "Joe", "Joseph"])
    resp = client.post("/player", json={"name": f"{n}{i}", **data})
    assert resp.status_code == 200
    return Player(**resp.json())


async def amkplayer(aclient: AsyncClient, p: Player):
    return Player(**(await aclient.post("/player", json=p.model_dump())).json())


def test_create_battle(client: TestClient):
    counter = cnt()
    p1 = make_player(client, next(counter), {})
    p2 = make_player(client, next(counter), {"defense": 20})
    resp = client.post(f"/battle/{p1.id}/{p2.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["winner"]["name"] == p1.name


def test_battle_lock_stat_present(client: TestClient):
    counter = cnt()
    p1 = make_player(client, next(counter), {})
    p2 = make_player(client, next(counter), {"defense": 20})
    resp = client.post(f"/battle/{p1.id}/{p2.id}")
    assert resp.status_code == 200
    assert resp.headers[settings.STAT_HEADER] is not None


def test_create_battle_fails_nonexist_player(client: TestClient):
    resp = client.post("/battle/12/999")
    assert resp.status_code == 404


def test_victory(client: TestClient):
    counter = cnt()
    p1 = make_player(client, next(counter), {"attack": 70, "defense": 50})
    p2 = make_player(client, next(counter), {"attack": 50, "defense": 30})
    resp = client.post(f"/battle/{p1.id}/{p2.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["winner"]["name"] == p1.name

    p1 = make_player(client, next(counter), {"attack": 20, "defense": 20})
    p2 = make_player(client, next(counter), {"attack": 50, "defense": 30})
    resp = client.post(f"/battle/{p1.id}/{p2.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["winner"]["name"] == p2.name


async def test_concurrent(
    aclient: AsyncClient, db_sessionmaker: async_sessionmaker[AsyncSession]
):
    p100 = await amkplayer(aclient, Player(name="p100", attack=100, defense=100))
    p1 = await amkplayer(aclient, Player(name="p1", attack=50, defense=60))
    p2 = await amkplayer(aclient, Player(name="p2", attack=70, defense=80))
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
        btasks.append(asyncio.create_task(aclient.post(f"/battle/{p1.id}/{p2.id}")))

    bresps = await asyncio.gather(*btasks)
    for i in range(len(battles)):
        assert bresps[i].json()["winner"]["name"] == battles[i][2].name

    # All players should be unlocked
    async with db_sessionmaker() as db:
        for p in (await db.exec(select(Player))).all():
            assert p.battle_lock == False


def test_leaderboard(client: TestClient | httpx2.Client, battle_path="/battle"):
    counter = cnt()
    p1 = make_player(client, next(counter), {"attack": 80, "defense": 60})
    p2 = make_player(client, next(counter), {"attack": 60, "defense": 30})
    p3 = make_player(client, next(counter), {"attack": 40, "defense": 20})
    p4 = make_player(client, next(counter), {"attack": 80, "defense": 70})

    resp = client.post(f"{battle_path}/{p1.id}/{p2.id}")
    assert resp.status_code == 200

    resp = client.get("/leaderboard")
    assert resp.status_code == 200
    data = resp.json()

    assert len(data) == 1
    assert data[0]["player"]["id"] == p1.id

    client.post(f"{battle_path}/{p3.id}/{p1.id}")
    client.post(f"{battle_path}/{p4.id}/{p1.id}")
    client.post(f"{battle_path}/{p3.id}/{p4.id}")

    resp = client.get("/leaderboard")
    assert resp.status_code == 200
    data = resp.json()

    assert len(data) == 2
    assert data[0]["score"] > data[1]["score"]


def test_security(client: TestClient):
    h = client.headers
    client.headers = {}
    resp = client.post("/player", json={"name": "joe"})
    assert resp.status_code == 401
    client.headers = h


def wait_for_string(stream: IO[Any], pattern: str):
    for line in iter(stream.readline, b""):
        if pattern in line:
            break


def test_defer(db):
    if not os.getenv("WITH_REDIS"):
        return
    env = {"DB_URL": settings.DB_URL}
    redis = subprocess_wait_for(
        ["docker", "run", "-p", "6379:6379", "redis:8"],
        "Ready to accept",
        env=env,
    )
    worker = subprocess_wait_for(
        ["uv", "run", "taskiq", "worker", "battle_engine.tasks:broker"],
        "Started process worker",
        env=env,
    )
    server = subprocess_wait_for(
        ["uv", "run", "fastapi", "dev"],
        "Uvicorn running",
        env=env,
    )
    sleep(1)
    try:
        client = httpx2.Client(
            base_url="http://localhost:8000",
            headers={settings.API_KEY_HEADER: settings.API_KEY_SECRET},
        )
        test_leaderboard(client, "/battle_defer")
    finally:
        server.terminate()
        worker.terminate()
        server.wait()
        worker.wait()
        redis.terminate()
        redis.wait()
