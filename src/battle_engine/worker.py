import asyncio
import logging
import os
import sys
from asyncio.queues import Queue

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from battle_engine.db import get_engine, init_models
from battle_engine.logic import process_battle
from battle_engine.models import BattleRequest, BattleStatus

load_dotenv()

DB_URL = os.getenv("DB_URL")
log = logging.getLogger("worker")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)


async def read_battles(
    db: async_sessionmaker[AsyncSession], tasks: Queue[BattleRequest], batch=16
):
    log.info("Polling for new battle requests")
    while True:
        async with db() as sess:
            for _ in range(batch):
                req = await BattleRequest.pop(sess)
                if req is not None:
                    log.info(f"R: Read battle {req.id} from DB, pushing to queue")
                    await tasks.put(req)
                else:
                    break
        await asyncio.sleep(1 / 30)


async def worker(
    db: async_sessionmaker[AsyncSession], tasks: Queue[BattleRequest], id: int
):
    log.info(f"Worker {id} starting...")
    while True:
        req = await tasks.get()
        assert req.id is not None
        async with db() as sess:
            battle = await BattleRequest.get(sess, req.id)
            assert battle is not None
            log.info(f"W{id}: Processing battle {battle.id}")
            process_battle(battle)
            await battle.release(sess)


async def amain(pool_size=8):
    log.info("Worker starting...")
    if not DB_URL:
        print("Missing DB_URL env. var", file=sys.stderr)
        sys.exit(1)

    tasks = Queue(1000)
    engine = get_engine(DB_URL)
    session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    await init_models(engine)

    reader = asyncio.create_task(read_battles(session, tasks))
    workers = [asyncio.create_task(worker(session, tasks, i)) for i in range(pool_size)]
    await asyncio.gather(reader, *workers)


def main():
    asyncio.run(amain())


if __name__ == "__main__":
    main()
