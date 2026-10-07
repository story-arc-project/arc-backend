import hashlib

from pydantic import EmailStr


type HashEmail = str

def hash_email(email: EmailStr) -> HashEmail:
    return hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()
