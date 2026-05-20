from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError, ValidationException
from fastapi.middleware.cors import CORSMiddleware
from os import getenv

from fastapi.responses import JSONResponse
from src.api.analysis import analysis_router
from src.api.experiences import experiences_router
from src.api.export import export_router
from src.api.internal import internal_router
from src.api.libraries import libraries_router
from src.api.models.exc import AppException
from src.api.presets import presets_router
from src.db.db import create_db_and_tables
from src.api.auth import auth_router, remove_tokens
from src.enums import ErrorResponseCode

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
    response = JSONResponse(
        status_code = exc.status_code,
        content = exc.error.model_dump()
    )
    if response.status_code == 403 and exc.error.code in [ErrorResponseCode.AUTH_REVOKED, ErrorResponseCode.AUTH_REUSE_DETECTED]:
        remove_tokens(response)
    return response

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: ValidationException):
    return JSONResponse(
        status_code = 400,
        content = {
            "status": "error",
            "code": "INVALID_INPUT",
            "message": "Please provide a valid input.",
            "data": {
                "invalid_fields": [err["loc"][-1] for err in exc.errors()]
            }
        }
    )

app.include_router(
    internal_router,
    prefix=f"/{getenv("INTERNAL_ROUTE", "internal")}"
)
app.include_router(
    auth_router,
    prefix="/auth"
)
app.include_router(
    experiences_router,
    prefix="/experiences"
)
app.include_router(
    libraries_router,
    prefix="/libraries"
)
app.include_router(
    presets_router,
    prefix="/presets"
)
app.include_router(
    analysis_router,
    prefix="/analysis"
)
app.include_router(
    export_router,
    prefix="/export"
)