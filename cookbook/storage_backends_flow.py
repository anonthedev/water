"""
Cookbook: Configuring flows with different storage backends
==========================================================

Water supports multiple storage backends out of the box.  This example
shows how to wire up each one.

Backends available:
  - InMemoryStorage   (built-in, no dependencies)
  - SQLiteStorage     (built-in, uses stdlib sqlite3)
  - RedisStorage      (requires ``pip install redis``)
  - PostgresStorage   (requires ``pip install asyncpg``)
"""

import asyncio
from water import Flow, create_task, InMemoryStorage, SQLiteStorage


# ---------------------------------------------------------------------------
# 1. Define some simple tasks
# ---------------------------------------------------------------------------

@create_task(name="greet")
async def greet(data):
    name = data.get("name", "World")
    return {"message": f"Hello, {name}!"}


@create_task(name="shout")
async def shout(data):
    return {"message": data["message"].upper()}


# ---------------------------------------------------------------------------
# 2. In-memory storage (default, good for tests / ephemeral runs)
# ---------------------------------------------------------------------------

memory_flow = Flow(
    name="memory_flow",
    storage=InMemoryStorage(),
)
memory_flow.add_task(greet)
memory_flow.add_task(shout)


# ---------------------------------------------------------------------------
# 3. SQLite storage (built-in, persists to a local file)
# ---------------------------------------------------------------------------

sqlite_flow = Flow(
    name="sqlite_flow",
    storage=SQLiteStorage(db_path="my_flows.db"),
)
sqlite_flow.add_task(greet)
sqlite_flow.add_task(shout)


# ---------------------------------------------------------------------------
# 4. Redis storage (requires `pip install redis`)
# ---------------------------------------------------------------------------

def make_redis_flow() -> Flow:
    from water import RedisStorage

    redis_flow = Flow(
        name="redis_flow",
        storage=RedisStorage(
            redis_url="redis://localhost:6379",
            prefix="myapp",
        ),
    )
    redis_flow.add_task(greet)
    redis_flow.add_task(shout)
    return redis_flow


# ---------------------------------------------------------------------------
# 5. PostgreSQL storage (requires `pip install asyncpg`)
# ---------------------------------------------------------------------------

async def make_postgres_flow() -> Flow:
    from water import PostgresStorage

    storage = PostgresStorage(dsn="postgresql://user:password@localhost:5432/mydb")
    # IMPORTANT: call initialize() once to create the tables
    await storage.initialize()

    pg_flow = Flow(
        name="postgres_flow",
        storage=storage,
    )
    pg_flow.add_task(greet)
    pg_flow.add_task(shout)
    return pg_flow


# ---------------------------------------------------------------------------
# Run the in-memory example
# ---------------------------------------------------------------------------

async def main():
    # In-memory example (always works)
    result = await memory_flow.run({"name": "Water"})
    print("InMemory result:", result)

    # SQLite example (always works)
    result = await sqlite_flow.run({"name": "Water"})
    print("SQLite result:", result)

    # Uncomment the following to try Redis (needs a running Redis server):
    # redis_flow = make_redis_flow()
    # result = await redis_flow.run({"name": "Water"})
    # print("Redis result:", result)

    # Uncomment the following to try PostgreSQL (needs a running PG server):
    # pg_flow = await make_postgres_flow()
    # result = await pg_flow.run({"name": "Water"})
    # print("Postgres result:", result)


if __name__ == "__main__":
    asyncio.run(main())
