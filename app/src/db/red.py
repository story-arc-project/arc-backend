from pydantic import EmailStr
import redis

from src.const import VERIFICATION_CODE_EXPIRE, VERIFICATION_MAX_ATTEMPTS

r = redis.Redis("redis", 6379, decode_responses=True)

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