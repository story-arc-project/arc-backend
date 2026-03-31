from contextlib import asynccontextmanager
from fastapi import FastAPI
from src.db.db import create_db_and_tables
from src.api.auth import auth_router

@asynccontextmanager
async def lifespan(app: FastAPI):  # pyright: ignore[reportUnusedParameter]
    create_db_and_tables()
    yield

app = FastAPI(lifespan=lifespan)

app.include_router(
    auth_router,
    prefix="/auth"
)