from fakeredis import FakeRedis

from src.db.red import store_code, get_code, delete_code
from src.const import VERIFICATION_MAX_ATTEMPTS

EMAIL = "a@test.com"
CODE = "123456"
PURPOSE = "verify"

class TestStoreAndGet:
    def test_store_then_get_returns_code(self, fake_redis: FakeRedis):
        store_code(EMAIL, CODE, PURPOSE)
        assert get_code(EMAIL, PURPOSE) == CODE

    def test_overwrite_code(self, fake_redis: FakeRedis):
        store_code(EMAIL, CODE, PURPOSE)
        store_code(EMAIL, "999999", PURPOSE)
        assert get_code(EMAIL, PURPOSE) == "999999"

    def test_get_nonexistent_returns_none(self, fake_redis: FakeRedis):
        assert get_code(EMAIL, PURPOSE) is None

class TestDeleteCode:
    def test_delete_removes_verify_key(self, fake_redis: FakeRedis):
        store_code(EMAIL, CODE, PURPOSE)
        delete_code(EMAIL, PURPOSE)
        assert get_code(EMAIL, PURPOSE) is None

    def test_delete_removes_limit_key(self, fake_redis: FakeRedis):
        store_code(EMAIL, CODE, PURPOSE)
        delete_code(EMAIL, PURPOSE)
        assert fake_redis.get(f"limit:{EMAIL}") is None

    def test_delete_idempotent(self, fake_redis: FakeRedis):
        store_code(EMAIL, CODE, PURPOSE)
        delete_code(EMAIL, PURPOSE)
        delete_code(EMAIL, PURPOSE)  # should not raise
        assert get_code(EMAIL, PURPOSE) is None

class TestTTL:
    def test_verify_key_has_ttl(self, fake_redis: FakeRedis):
        store_code(EMAIL, CODE, PURPOSE)
        ttl = fake_redis.ttl(f"verify:{EMAIL}")
        assert isinstance(ttl, int)
        assert ttl > 0

    def test_limit_key_has_ttl(self, fake_redis: FakeRedis):
        store_code(EMAIL, CODE, PURPOSE)
        ttl = fake_redis.ttl(f"limit:{EMAIL}")
        assert isinstance(ttl, int)
        assert ttl > 0