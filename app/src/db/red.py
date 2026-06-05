from pydantic import EmailStr
import redis

from src.const import VERIFICATION_CODE_EXPIRE, VERIFICATION_MAX_ATTEMPTS, RETRY_COOLDOWN

r = redis.Redis("redis", 6379, decode_responses=True)

COOLDOWN_SECONDS = RETRY_COOLDOWN * 60

def _verify_keygen(email: EmailStr):
    return f"verify:{email}"

def _limit_keygen(email: EmailStr):
    return f"limit:{email}"

def store_code(email: EmailStr, code: str):
    _ = r.set(_verify_keygen(email), code, int(VERIFICATION_CODE_EXPIRE * 60))
    _ = r.set(_limit_keygen(email), VERIFICATION_MAX_ATTEMPTS, int(VERIFICATION_CODE_EXPIRE * 60))

def get_code(email: EmailStr):
    return r.get(_verify_keygen(email))

def delete_code(email: EmailStr):
    _ = r.delete(_verify_keygen(email))
    _ = r.delete(_limit_keygen(email))

def decr_limit(email: EmailStr):
    decr_value = r.decr(_limit_keygen(email))
    if (not isinstance(decr_value, int)) or decr_value <= 0:
        delete_code(email)
        return 0
    return decr_value

def _get_cooldown_key(key: str):
    return f"cooldown:{key}"

def _get_attempts_key(key):
    return f"attempts:{key}"

def is_locked(key: str):
    ttl = r.ttl(_get_cooldown_key(key))
    if isinstance(ttl, int) and ttl > 0:
        return True, ttl
    return False, 0

def increment_attempt(key: str):
    count = r.incr(_get_attempts_key(key))
    if not isinstance(count, int):
        return None
    if count == 1:
        r.expire(_get_attempts_key(key), COOLDOWN_SECONDS)
    return count

def set_lockout(key: str):
    r.setex(_get_cooldown_key(key), COOLDOWN_SECONDS, 1)
    r.delete(_get_attempts_key(key))

def clear(key: str):
    r.delete(_get_attempts_key(key))
    r.delete(_get_cooldown_key(key))

def get_attempt_count(key: str):
    val = r.get(_get_attempts_key(key))
    if not isinstance(val, int):
        return 0
    return val