import hashlib

from pydantic import EmailStr


def hash_email(email: EmailStr) -> str:
    return hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()
