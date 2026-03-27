from contextlib import asynccontextmanager
from fastapi import FastAPI
from src.db import create_db_and_tables

@asynccontextmanager
async def lifespan(app: FastAPI):  # pyright: ignore[reportUnusedParameter]
    create_db_and_tables()
    yield

app = FastAPI(lifespan=lifespan)