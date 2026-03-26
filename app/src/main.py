from contextlib import asynccontextmanager
from fastapi import FastAPI
from src.db import engine
from src.models import Base

@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield

app = FastAPI(lifespan=lifespan)