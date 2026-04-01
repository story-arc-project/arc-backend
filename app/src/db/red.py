from pydantic import EmailStr
import redis

from src.const import VERIFICATION_CODE_EXPIRE

r = redis.Redis("redis", 6379, decode_responses=True)

def _keygen(email: EmailStr):
    return f"verify:{email}"

def store_code(email: EmailStr, code: str):
    _ = r.set(_keygen(email), code, VERIFICATION_CODE_EXPIRE * 60)

def get_code(email: EmailStr):
    return r.get(_keygen(email))

def delete_code(email: EmailStr):
    _ = r.delete(_keygen(email))