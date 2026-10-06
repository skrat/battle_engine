from fastapi.testclient import TestClient


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
