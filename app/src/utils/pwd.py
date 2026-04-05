from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher

hasher = PasswordHash([Argon2Hasher()])

def hash_password(password: str):
    return hasher.hash(password)

def verify_password(password: str, hashed: str):
    return hasher.verify(password, hashed)