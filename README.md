# ⚔️ Backend service for a battle engine

This was a home assignment from one my potential employers. I pushed it a little further and
developed a demo backend, with multiple options persistence and concurrency

### Requirements

 - Python 3.14 (could work with lower version, not tested)
 - uv for dependency management ([installation](https://docs.astral.sh/uv/#installation))
 - Redis, SQLite or PostgreSQL

### Running

Launch Redis, eg.:

```sh
docker-compose up
```

Inside project directory, install dependencies with:

```sh
uv sync
```

Run the test suite:

```sh
uv run pytest -s
```

Run the development server:

```sh
uv run fastapi dev
```

### Multiple backends

Using `env BACKEND=?` you can set the persistence/locking backend:
 - `battle_engine.backend.redis.impl:RedisBackend` or 
 - `battle_engine.backend.sql.impl:SQLBackend`

See `.env` for how to configure each.

### API documentation

After launching the server you can visit the OpenAPI documentation 
at [http://localhost:8000/docs](http://localhost:8000/docs).

## Design decisions

The stack this is built with:

 - FastAPI & guvicorn for HTTP server. Concurrently handles **player** and **battle** requests using
   [asyncio](https://docs.python.org/3/howto/a-conceptual-overview-of-asyncio.html),
 - Redis, or SQLite / PostgreSQL as a primary database
 - Pydantic for request schema validation

Optionally, there is a backend that processes battles in a separate, scalable worker process based
on Taskiq and Redis. More on that later. (`env WITH_TASKIQ=1`)

The key decision here is to process the battles in the HTTP request handler immediately upon
arrival. Thus the FIFO requirement, processing battles as they come, is satisfied. The fact that the
battle logic is small, thus making the battle procssing low CPU and IO intensity.

 ### Concurrent battle processing with non-overlapping players

This is achieved using Redis Lua scripting and watching player locking keys, ensuring no two players
can engage in concurrent battles. Lua scripts in Redis are atomic, ensuring consistency.

In the SQL backend, consistency is achieved using serialized transactions and "UPSERT" statements
for updating the leaderboard.

### Clean architecture

The app, although small, maps well to clean architectre layers:

 - **Entities** - [models.py](./src/battle_engine/models.py) (`PlayerBase`, `BattleRequest`,
   `BattleResult`, etc.)
 - **Use cases** - [logic.py](./src/battle_engine/logic.py) (only requires above mentioned entities)
 - **Frameworks and Drivers** - [main.py](./src/battle_engine/main.py) as web framework, everything
   in [backend](./src/battle_engine/backend/) for DB and persistence

### Running with Taskiq

This adds an extra level of indirection. Battles can be processed in a separate process,
independently scalable from the main HTTP server. I don't see a valid reason for this extra IO (task
-> Redis -> Worker; then Worker -> Redis -> Result to HTTP handler) in this case.

To run the worker process:

```sh
uv run taskiq worker battle_engine.tasks:broker
```

To run the server with Redis + Taskiq support:

```sh
env WITH_TASKIQ=1 uv run fastapi run
```

To utilize the Redis + Taskiq backend, use the `/battle_defer` endpoint. You can also run the test
suite and API tests, using:

```sh
env WITH_TASKIQ=1 uv run pytest -s tests/test_api.py
```

 ### Security

 Too keep things simple and within the scope of a home assignment, authentication is implemented
 using an API key. A shared secret between the client and the server. It can be configured through
 `.env` file or environment variables. It's using a conventional `X-API-Key` HTTP header to
 authenticate the client.

## Performance

You can run performance stress test using [Locust](https://docs.locust.io/en/stable/)

```sh
uv run locust -H http://localhost:8000
```

And in another terminal, run the server with

```sh 
uv run fastapi run # or with more parameters to play with (eg. --limit-concurrency) uv run
uvicorn battle_engine.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### Notes on the battle logic specification

The specification misses a few crucial point:

- does not specify whether a player's hit points are persisted, or reset (to 100?) at the start of
  each battle
- does not specify the behavior where both players' defense value is high enough to miss the attack.
  In this case, the player's roles will switch infinitely. I mitigated this by setting a limit to
  number of turns per battle.
