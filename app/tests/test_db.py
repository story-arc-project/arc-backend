from fakeredis import FakeRedis

from src.db.red import store_code, get_code, decr_limit, delete_code
from src.const import VERIFICATION_MAX_ATTEMPTS

EMAIL = "a@test.com"
CODE = "123456"

class TestStoreAndGet:
    def test_store_then_get_returns_code(self, fake_redis: FakeRedis):
        store_code(EMAIL, CODE)
        assert get_code(EMAIL) == CODE

    def test_overwrite_code(self, fake_redis: FakeRedis):
        store_code(EMAIL, CODE)
        store_code(EMAIL, "999999")
        assert get_code(EMAIL) == "999999"

    def test_get_nonexistent_returns_none(self, fake_redis: FakeRedis):
        assert get_code(EMAIL) is None

class TestDeleteCode:
    def test_delete_removes_verify_key(self, fake_redis: FakeRedis):
        store_code(EMAIL, CODE)
        delete_code(EMAIL)
        assert get_code(EMAIL) is None

    def test_delete_removes_limit_key(self, fake_redis: FakeRedis):
        store_code(EMAIL, CODE)
        delete_code(EMAIL)
        assert fake_redis.get(f"limit:{EMAIL}") is None

    def test_delete_idempotent(self, fake_redis: FakeRedis):
        store_code(EMAIL, CODE)
        delete_code(EMAIL)
        delete_code(EMAIL)  # should not raise
        assert get_code(EMAIL) is None

class TestDecrLimit:
    def test_decr_reduces_attempts(self, fake_redis: FakeRedis):
        store_code(EMAIL, CODE)
        remaining = decr_limit(EMAIL)
        assert remaining == VERIFICATION_MAX_ATTEMPTS - 1

    def test_decr_multiple_times(self, fake_redis: FakeRedis):
        store_code(EMAIL, CODE)
        remaining = None
        for _ in range(VERIFICATION_MAX_ATTEMPTS):
            remaining = decr_limit(EMAIL)
        assert remaining == 0

    def test_decr_to_zero_deletes_keys(self, fake_redis: FakeRedis):
        store_code(EMAIL, CODE)
        for _ in range(VERIFICATION_MAX_ATTEMPTS):
            decr_limit(EMAIL)
        assert fake_redis.get(f"verify:{EMAIL}") is None
        assert fake_redis.get(f"limit:{EMAIL}") is None

    def test_decr_does_not_go_negative(self, fake_redis: FakeRedis):
        store_code(EMAIL, CODE)
        for _ in range(VERIFICATION_MAX_ATTEMPTS + 1):
            decr_limit(EMAIL)
        # key was deleted at 0, so it should no longer exist
        assert fake_redis.get(f"limit:{EMAIL}") is None

class TestTTL:
    def test_verify_key_has_ttl(self, fake_redis: FakeRedis):
        store_code(EMAIL, CODE)
        ttl = fake_redis.ttl(f"verify:{EMAIL}")
        assert isinstance(ttl, int)
        assert ttl > 0

    def test_limit_key_has_ttl(self, fake_redis: FakeRedis):
        store_code(EMAIL, CODE)
        ttl = fake_redis.ttl(f"limit:{EMAIL}")
        assert isinstance(ttl, int)
        assert ttl > 0