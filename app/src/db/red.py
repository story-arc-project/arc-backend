from pydantic import EmailStr
import redis

from src.const import VERIFICATION_CODE_EXPIRE

r = redis.Redis("redis", 6379, decode_responses=True)

def _verify_keygen(email: EmailStr):
    return f"verify:{email}"

def store_code(email: EmailStr, code: str):
    _ = r.set(_verify_keygen(email), code, int(VERIFICATION_CODE_EXPIRE * 60))

def get_code(email: EmailStr):
    return r.get(_verify_keygen(email))

def delete_code(email: EmailStr):
    _ = r.delete(_verify_keygen(email))