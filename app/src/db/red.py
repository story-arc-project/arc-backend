from typing import Literal
from pydantic import EmailStr
import redis

from src.const import REDIS_HOST, REDIS_PORT, VERIFICATION_CODE_EXPIRE

MIN_IN_SEC = 60
PURPOSE_SCOPE = Literal["verify", "reset"]

r = redis.Redis(REDIS_HOST, REDIS_PORT, decode_responses=True)

def _verify_keygen(email: EmailStr, purpose: PURPOSE_SCOPE):
    return f"{purpose}:{email}"

def store_code(email: EmailStr, code: str, purpose: PURPOSE_SCOPE):
    _ = r.set(_verify_keygen(email, purpose), code, int(VERIFICATION_CODE_EXPIRE * MIN_IN_SEC))

def get_code(email: EmailStr, purpose: PURPOSE_SCOPE):
    return r.get(_verify_keygen(email, purpose))

def delete_code(email: EmailStr, purpose: PURPOSE_SCOPE):
    _ = r.delete(_verify_keygen(email, purpose))

def _get_cooldown_key(key: str):
    return f"cooldown:{key}"

def _get_attempts_key(key):
    return f"attempts:{key}"

def is_locked(key: str):
    ttl = r.ttl(_get_cooldown_key(key))
    if isinstance(ttl, int) and ttl > 0:
        return True, ttl
    return False, 0

def increment_attempt(key: str, cooldown_minutes: int):
    count = r.incr(_get_attempts_key(key))
    if not isinstance(count, int):
        return None
    if count == 1:
        r.expire(_get_attempts_key(key), cooldown_minutes * MIN_IN_SEC)
    return count

def set_lockout(key: str, cooldown_minutes: int):
    r.setex(_get_cooldown_key(key), cooldown_minutes * MIN_IN_SEC, 1)
    r.delete(_get_attempts_key(key))

def clear(key: str):
    r.delete(_get_attempts_key(key))
    r.delete(_get_cooldown_key(key))

def get_attempt_count(key: str):
    val = r.get(_get_attempts_key(key))
    if val is None:
        return 0
    try:
        return int(val)
    except:
        return None