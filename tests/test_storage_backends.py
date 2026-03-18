"""Tests for Redis and PostgreSQL storage backends.

Since Redis and PostgreSQL servers are unlikely to be available in a
typical test environment, we focus on verifying that the classes raise
a clear ``ImportError`` when their underlying driver packages are
missing, and that they can at least be imported and instantiated when
the drivers *are* present.
"""

import pytest


# ---------------------------------------------------------------------------
# Redis
# ---------------------------------------------------------------------------

def test_redis_storage_import_error():
    """RedisStorage() raises ImportError when 'redis' is not installed."""
    try:
        import redis  # noqa: F401
        pytest.skip("redis package is installed; cannot test ImportError path")
    except ImportError:
        pass

    from water.storage.redis import RedisStorage

    with pytest.raises(ImportError, match="redis"):
        RedisStorage()


def test_redis_storage_instantiates_when_redis_available():
    """If the redis package is available, RedisStorage can be instantiated."""
    pytest.importorskip("redis")

    from water.storage.redis import RedisStorage

    storage = RedisStorage(redis_url="redis://localhost:6379", prefix="test")
    assert storage._prefix == "test"


# ---------------------------------------------------------------------------
# PostgreSQL
# ---------------------------------------------------------------------------

def test_postgres_storage_import_error():
    """PostgresStorage() raises ImportError when 'asyncpg' is not installed."""
    try:
        import asyncpg  # noqa: F401
        pytest.skip("asyncpg package is installed; cannot test ImportError path")
    except ImportError:
        pass

    from water.storage.postgres import PostgresStorage

    with pytest.raises(ImportError, match="asyncpg"):
        PostgresStorage(dsn="postgresql://localhost/test")


def test_postgres_storage_instantiates_when_asyncpg_available():
    """If asyncpg is available, PostgresStorage can be instantiated."""
    pytest.importorskip("asyncpg")

    from water.storage.postgres import PostgresStorage

    storage = PostgresStorage(dsn="postgresql://localhost/test")
    assert storage._dsn == "postgresql://localhost/test"
