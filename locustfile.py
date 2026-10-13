import os
import random
import threading
import time
from collections import defaultdict
from random import randbytes

from locust import FastHttpUser, between, events, task
from requests import Response

from battle_engine.settings import settings

TIMEOUT = 5
HEADERS = {settings.API_KEY_HEADER: settings.API_KEY_SECRET}
BATTLE_PATH = "/battle_defer" if os.getenv("WITH_REDIS") else "/battle"


class CustomMetrics:
    def __init__(self):
        self.lock = threading.Lock()
        self.metrics = defaultdict(list)

    def record(self, name: str, value: float):
        with self.lock:
            self.metrics[name].append({"value": value, "timestamp": time.time()})

    def get_stats(self, name: str):
        with self.lock:
            values = [m["value"] for m in self.metrics[name]]
            if not values:
                return None
            return {
                "count": len(values),
                "min": min(values),
                "max": max(values),
                "avg": sum(values) / len(values),
            }


custom_metrics = CustomMetrics()


@events.request.add_listener
def on_request(
    request_type,
    name,
    response_time,
    response_length,
    response: Response,
    context,
    exception,
    start_time,
    url,
    **kwargs,
):
    """Track additional data on every request."""
    if response is not None and settings.STAT_HEADER in response.headers:
        num_attempts = int(response.headers[settings.STAT_HEADER])
        custom_metrics.record("num_lock_attempts", num_attempts)


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Print custom metrics summary when test ends."""
    print("\n--- Custom Metrics Summary ---")
    stats = custom_metrics.get_stats("num_lock_attempts")
    if stats:
        print("Player lock stats (number of lock attempts):")
        print(f"  Count: {stats['count']}")
        print(f"  Min: {stats['min']:.2f}")
        print(f"  Max: {stats['max']:.2f}")
        print(f"  Avg: {stats['avg']:.2f}")


def make_player():
    n = f"Joe{randbytes(8).hex()}"
    return {"name": n}


class BattleEngine(FastHttpUser):
    wait_time = between(1, 5)
    network_timeout = TIMEOUT
    connection_timeout = TIMEOUT

    def __init__(self, environment) -> None:
        super().__init__(environment)
        self.players = []

    def post_player(self):
        return self.client.post(
            "/player",
            json=make_player(),
            headers=HEADERS,
        ).json()["pk"]

    def post_battle(self, p1: int, p2: int):
        self.client.request_name = f"{BATTLE_PATH}/[p1]/[p2]"
        self.client.post(
            f"{BATTLE_PATH}/{p1}/{p2}",
            headers=HEADERS,
        )
        self.client.request_name = None

    @task(1)
    def create_player(self):
        self.players.append(self.post_player())

    @task(10)
    def create_battle(self):
        if len(self.players) > 1:
            p1 = random.choice(self.players)
            p2 = p1
            while p2 is p1:
                p2 = random.choice(self.players)
            self.post_battle(p1, p2)

    @task(1)
    def get_leaderboard(self):
        self.client.get("/leaderboard", headers=HEADERS)
