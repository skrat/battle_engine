import random
from collections.abc import Generator

from fastapi.testclient import TestClient

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


def make_player(client: TestClient) -> Generator[int]:
    cnt = 0
    while True:
        n = random.choice(["Jane", "Joe", "Joseph"])
        resp = client.post("/player", json={"name": f"{n}{cnt}"})
        assert resp.status_code == 200
        yield resp.json()["id"]
        cnt += 1


def test_create_battle(client: TestClient):
    players = make_player(client)
    p1 = next(players)
    p2 = next(players)
    resp = client.post(f"/battle/{p1}/{p2}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["initiator_id"] == p1
    assert data["opponent_id"] == p2


def test_create_battle_fails_nonexist_player(client: TestClient):
    players = make_player(client)
    p1 = next(players)
    resp = client.post(f"/battle/{p1}/999")
    assert resp.status_code == 422
