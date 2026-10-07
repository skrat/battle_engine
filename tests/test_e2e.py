import asyncio
import os
import random
import subprocess
from time import sleep

import httpx2
import pytest
from dotenv import load_dotenv

from tests.util import random_player

load_dotenv()

DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASS")
DB_DATABASE = os.getenv("DB_DATABASE")


@pytest.fixture
def postgres_docker():
    print("Running PostgreSQL in a Docker container, this may take a while...")
    pg_id = subprocess.run(
        [
            "docker",
            "run",
            "--name",
            "pg-cont",
            "-e",
            f"POSTGRES_USER={DB_USER}",
            "-e",
            f"POSTGRES_PASSWORD={DB_PASS}",
            "-e",
            f"POSTGRES_DB={DB_DATABASE}",
            "-p",
            "5432:5432",
            "-d",
            "postgres",
        ],
        capture_output=True,
        check=True,
    ).stdout.decode()
    sleep(1)
    yield
    subprocess.run(["docker", "stop", pg_id], check=True, capture_output=True)
    subprocess.run(["docker", "rm", pg_id], check=True, capture_output=True)


@pytest.fixture
def app_procs():
    server = subprocess.Popen(["uv", "run", "fastapi", "run"])
    worker = subprocess.Popen(["uv", "run", "worker"])
    sleep(1)
    yield
    server.terminate()
    worker.terminate()


@pytest.mark.asyncio
async def test_with_subprocess(postgres_docker, app_procs):
    async with httpx2.AsyncClient(base_url="http://localhost:8000") as c:
        p1 = await c.post("/player", json={"name": "joe", "defense": 50, "attack": 80})
        assert p1.status_code == 200
        p1_id = p1.json()["id"]
        assert p1_id is not None
        p2 = await c.post("/player", json={"name": "jane", "defense": 50, "attack": 20})
        assert p2.status_code == 200
        p2_id = p2.json()["id"]
        assert p2_id is not None

        b0 = await c.post(f"/battle/{p1_id}/{p2_id}")
        assert b0.json()["id"] is not None

        players = await asyncio.gather(
            *[
                asyncio.create_task(
                    c.post("/player", json=random_player(i).model_dump())
                )
                for i in range(10)
            ]
        )
        players_ids: list[int] = [p.json()["id"] for p in players]

        battles_tsks: list[asyncio.Task] = []
        for _ in range(30):
            p1 = random.choice(players_ids)
            p2 = p1
            while p2 == p1:
                p2 = random.choice(players_ids)
            battles_tsks.append(asyncio.create_task(c.post(f"/battle/{p1}/{p2}")))
        battles_resps = await asyncio.gather(*battles_tsks)
