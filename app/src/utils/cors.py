from fastapi import Request
from os import getenv

def check_cors(request: Request):
    origin = request.headers.get("origin")
    if origin is not None and origin in getenv("FRONTEND_HOSTS", "").split(","):
        return origin
    return None