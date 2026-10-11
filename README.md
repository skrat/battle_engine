# Backend service for a battle engine

### Requirements

 - Python 3.14 (could work with lower version, not tested)
 - uv for dependency management ([installation](https://docs.astral.sh/uv/#installation))
 - [Docker](https://docs.docker.com/engine/install/) - optional - if you want to test deferred battle processing with [Taskiq](https://taskiq-python.github.io/) and [Redis]()
 - [PostgreSQL](https://www.postgresql.org/) - optional

### Running

Inside project directory, install dependencies with:

```sh
uv sync
```

Run the test suite:

```sh
uv run pytest -s
```

Test suite is using SQLite for simplicity of setup. PostgreSQL can be used to run the
performance tests (see below). Database URL has to be configured in `.env` file or
using environment variables.

Run the development server:

```sh
uv run fastapi dev
```

### API documentation

After launching the server you can visit the OpenAPI documentation 
at [http://localhost:8000/docs](http://localhost:8000/docs).

## Design decisions

The stack this is built with consists of:

 - FastAPI & guvicorn for HTTP server. Concurrently handles **player** and **battle** requests using [asyncio](https://docs.python.org/3/howto/a-conceptual-overview-of-asyncio.html),
 - SQLModel + SQLAlchemy for ORM and database access
 - Async DB drivers for SQLite and PostgreSQL
 - Pydantic for request schema validation

 Optionally, there is a backend that processes battles in a separate, scalable worker process
 based on Taskiq and Redis. More on that later.

 The key decision here is to process the battles in the HTTP request handler immediately
 upon arrival. Thus the FIFO requirement, processing battles as they come, is satisfied.
 The fact that the battle logic is small, thus making the battle procssing low CPU and
IO intensity.

 ### Concurrent battle processing with non-overlapping players

Since this is using SQL RDMS as a backend data store, we can leverage SQL transactions and row-level locking. The key point here is to use a column in the Player table, that indicates whether the player is in an active battle. When we receive a battle request and we successfully acquire both players (locking them in the process), we process the battle, and then unlock the players. In case we are unable to get both players, the engine waits a fixed amount of time, and re-tries acquiring the players.

In practice, this is done using an SQL transaction, with a query similar to this:

```SQL
UPDATE player 
WHERE id IN (p1, p2) AND battle_lock = FALSE
SET battle_lock = TRUE
RETURNING *
```

During this transaction, we check whether the number of rows returned is 2 (p1 and p2). If we succeed, we process the battle. If we fail, we rollback the transaction, wait a fixed amount of time, and retry. Additionally, this requires SERIALIZABLE transactions, accepting that there is a performance penalty for doing so.

### Running with PostgreSQL

Run the database in a container:

```sh
docker run --name postgres-container -e POSTGRES_USER=myuser -e POSTGRES_PASSWORD=mypassword -e POSTGRES_DB=mydatabase -p 5432:5432 -d postgres
```

Edit `.env` file, comment out the `DB_URL` with SQLite, and uncomment the one with PostgreSQL.

### Running with Redis

This adds an extra level of indirection. Battles can be processed in a separate process, independently scalable from the main HTTP server. I don't see a valid reason for this extra IO (task -> Redis -> Worker; then Worker -> Redis -> Result to HTTP handler) in this case.

To run the worker process:

```sh
uv run taskiq worker battle_engine.tasks:broker
```

To run the server with Redis + Taskiq support:

```sh
env WITH_REDIS=1 uv run fastapi run
```

To utilize the Redis + Taskiq backend, use the `/battle_defer` endpoint. You can also run the
test suite and API tests, using:

```sh
env WITH_REDIS=1 uv run pytest -s tests/test_api.py
```

 ### Security

 Too keep things simple and within the scope of a home assignment, authentication is
 implemented using an API key. A shared secret between the client and the server. It
 can be configured through `.env` file or environment variables. It's using a conventional
 `X-API-Key` HTTP header to authenticate the client.

## Performance

You can run performance stress test using [Locust](https://docs.locust.io/en/stable/)

```sh
uv run locust -H http://localhost:8000
```

And in another terminal, run the server with

```sh
uv run fastapi run
# or with more parameters to play with (eg. --limit-concurrency)
uv run uvicorn battle_engine.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### SQLite + aiosqlite

(With uvicorn's 8 workers, single machine)

With SQLite, at certain higher rate of traffic, the DB was starting to lock up.
Without additional setup, SQLite doesn't allow concurrent writes and is thus the
choke point of the entire system.

But, surprisingly, performs quite well under local testing conditions.

### PostgreSQL + asyncpg

1. _With uvicorn's 8 workers, single machine, ~357 RPS, 4750 users_

   At certain higher rate of traffic, the DB driver started reporting
   too many connections.
    
2. _With uvicorn's 4 worker, single machine, ~385 RPS_
  
   QueuePool limit of size 5 overflow 10 reached, connection timed out.
   This is again a DB connection pool error.

3. _Increased the pool size to pool_size = 10, max_overflow = 20_

   Got to 5000 concurrent users before getting `asyncpg.exceptions.TooManyConnectionsError`
   and ~360 RPS.

This is all with a locally running PostgreSQL (inside Docker container) presumable with some
default cap on the number of client connections. So to increase the performance locally, you
need to first increase `max_connections`.

### Notes on the battle logic specification

The specification misses a few crucial point:

- does not specify whether a player's hit points are persisted, or reset (to 100?) at the start of each battle
- does not specify the behavior where both players' defense value is high enough to miss the attack. In this case, the player's roles will switch infinitely. I mitigated this by setting a limit to number of turns per battle.
