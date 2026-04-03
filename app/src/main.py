from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from os import getenv

from fastapi.responses import JSONResponse
from src.api.models.exc import AppException
from src.db.db import create_db_and_tables
from src.api.auth import auth_router

@asynccontextmanager
async def lifespan(app: FastAPI):  # pyright: ignore[reportUnusedParameter]
    create_db_and_tables()
    yield

app = FastAPI(lifespan=lifespan)

origins = getenv("FRONTEND_HOSTS", "").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    return JSONResponse(
        status_code = exc.status_code,
        content = exc.error.model_dump()
    )

app.include_router(
    auth_router,
    prefix="/auth"
)