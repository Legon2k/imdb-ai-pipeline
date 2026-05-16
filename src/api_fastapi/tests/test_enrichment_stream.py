import json
import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class HTTPException(Exception):
    def __init__(self, status_code, detail):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class FastAPI:
    def __init__(self, *args, **kwargs):
        pass

    def get(self, *args, **kwargs):
        return lambda func: func

    def post(self, *args, **kwargs):
        return lambda func: func


def query(default, **kwargs):
    return default


fastapi_module = types.ModuleType("fastapi")
fastapi_module.FastAPI = FastAPI
fastapi_module.HTTPException = HTTPException
fastapi_module.Query = query
responses_module = types.ModuleType("fastapi.responses")
responses_module.StreamingResponse = object
pydantic_module = types.ModuleType("pydantic")
pydantic_module.BaseModel = object
asyncpg_module = types.ModuleType("asyncpg")
pandas_module = types.ModuleType("pandas")
redis_module = types.ModuleType("redis")
redis_asyncio_module = types.ModuleType("redis.asyncio")
redis_asyncio_module.Redis = object
redis_module.asyncio = redis_asyncio_module

sys.modules.setdefault("fastapi", fastapi_module)
sys.modules.setdefault("fastapi.responses", responses_module)
sys.modules.setdefault("pydantic", pydantic_module)
sys.modules.setdefault("asyncpg", asyncpg_module)
sys.modules.setdefault("pandas", pandas_module)
sys.modules.setdefault("redis", redis_module)
sys.modules.setdefault("redis.asyncio", redis_asyncio_module)

import main as api_main  # noqa: E402


class FakeTransaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakeConnection:
    def __init__(self, pending_movies):
        self.pending_movies = pending_movies
        self.fetch_calls = []
        self.execute_calls = []

    def transaction(self):
        return FakeTransaction()

    async def fetch(self, query, *args):
        self.fetch_calls.append((query, args))
        return self.pending_movies

    async def execute(self, query, *args):
        self.execute_calls.append((query, args))
        return "UPDATE 2"


class FakeAcquire:
    def __init__(self, connection):
        self.connection = connection

    async def __aenter__(self):
        return self.connection

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakeDbPool:
    def __init__(self, connection):
        self.connection = connection

    def acquire(self):
        return FakeAcquire(self.connection)


class FakePipeline:
    def __init__(self, should_fail=False):
        self.should_fail = should_fail
        self.xadd_calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def xadd(self, stream_name, fields):
        self.xadd_calls.append((stream_name, fields))

    async def execute(self):
        if self.should_fail:
            raise RuntimeError("redis unavailable")
        return ["1-0" for _ in self.xadd_calls]


class FakeRedis:
    def __init__(self, should_fail=False):
        self.pipeline_instance = FakePipeline(should_fail=should_fail)

    def pipeline(self, transaction=True):
        self.transaction = transaction
        return self.pipeline_instance


class EnrichmentStreamTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.original_db_pool = api_main.db_pool
        self.original_redis_client = api_main.redis_client
        self.original_stream_name = api_main.AI_STREAM_NAME
        api_main.AI_STREAM_NAME = "ai_stream_test"

    def tearDown(self):
        api_main.db_pool = self.original_db_pool
        api_main.redis_client = self.original_redis_client
        api_main.AI_STREAM_NAME = self.original_stream_name

    async def test_enrich_movies_locks_pending_movies_and_publishes_stream_tasks(self):
        pending_movies = [
            {"id": 1, "rank": 1, "title": "First Movie", "rating": 9.3},
            {"id": 2, "rank": 2, "title": "Second Movie", "rating": 9.2},
        ]
        connection = FakeConnection(pending_movies)
        redis_client = FakeRedis()
        api_main.db_pool = FakeDbPool(connection)
        api_main.redis_client = redis_client

        response = await api_main.enrich_movies(limit=2)

        self.assertEqual(response["queued_tasks"], 2)
        lock_query, lock_args = connection.fetch_calls[0]
        self.assertIn("FOR UPDATE SKIP LOCKED", lock_query)
        self.assertEqual(lock_args, (2,))
        self.assertTrue(redis_client.transaction)
        self.assertEqual(len(redis_client.pipeline_instance.xadd_calls), 2)

        stream_name, fields = redis_client.pipeline_instance.xadd_calls[0]
        self.assertEqual(stream_name, "ai_stream_test")
        payload = json.loads(fields["payload"])
        self.assertEqual(payload["id"], 1)
        self.assertEqual(payload["title"], "First Movie")
        self.assertEqual(payload["rating"], 9.3)

    async def test_enrich_movies_reverts_locks_when_stream_publish_fails(self):
        pending_movies = [
            {"id": 10, "rank": 10, "title": "Locked Movie", "rating": 8.8},
            {"id": 11, "rank": 11, "title": "Another Locked Movie", "rating": 8.7},
        ]
        connection = FakeConnection(pending_movies)
        api_main.db_pool = FakeDbPool(connection)
        api_main.redis_client = FakeRedis(should_fail=True)

        with self.assertRaises(HTTPException) as raised:
            await api_main.enrich_movies(limit=2)

        self.assertEqual(raised.exception.status_code, 503)
        rollback_query, rollback_args = connection.execute_calls[0]
        self.assertIn("SET status = 'pending'", rollback_query)
        self.assertEqual(rollback_args, ([10, 11],))


if __name__ == "__main__":
    unittest.main()
