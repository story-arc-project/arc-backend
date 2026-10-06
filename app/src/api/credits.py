from fastapi import APIRouter

from src.const import PACKAGES

credits_router = APIRouter()

@credits_router.get("/packages")
def get_credit_packages():
    return {"packages": PACKAGES}