from fastapi import Depends, FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from os import getenv

from fastapi.responses import JSONResponse
from src.api.admin import admin_router
from src.api.analysis import analysis_router
from src.api.docs import docs_router
from src.api.experiences import experiences_router
from src.api.export import export_router
from src.api.feedback import feedback_router
from src.api.files import files_router
from src.api.internal import internal_router
from src.api.libraries import libraries_router
from src.api.models.exc import AppException
from src.api.presets import presets_router
from src.api.auth import auth_router, remove_tokens
from src.const import ADMIN_PAGE_NOT_ALLOWED
from src.enums import ErrorResponseCode
from src.logging import setup_logging
from src.utils.admin import require_admin

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
api_error_logger = setup_logging()

origins = getenv("FRONTEND_HOSTS", "").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)


@app.middleware("http")
async def log_unsuccessful_api_responses(request: Request, call_next):
    try:
        response = await call_next(request)
    except Exception:
        api_error_logger.exception(
            "API request failed method=%s path=%s status=500 client=%s",
            request.method,
            request.url.path,
            request.client.host if request.client else "unknown",
        )
        raise

    if response.status_code >= 500:
        api_error_logger.error(
            "API response method=%s path=%s status=%s client=%s",
            request.method,
            request.url.path,
            response.status_code,
            request.client.host if request.client else "unknown",
        )
    return response

@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    if exc.error.message == ADMIN_PAGE_NOT_ALLOWED:
        return Response(
            status_code = exc.status_code,
            content = '{"detail":"Not Found"}'
        )
    response = JSONResponse(
        status_code = exc.status_code,
        content = exc.error.model_dump()
    )
    if response.status_code == 403 and exc.error.code in [ErrorResponseCode.AUTH_REVOKED, ErrorResponseCode.AUTH_REUSE_DETECTED]:
        remove_tokens(response)
    return response

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = exc.errors()
    if any(err["msg"] == "Value error, WEAK_PASSWORD" for err in errors):
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "code": "WEAK_PASSWORD",
                "message": "Password must be at least 8 characters and include both letters and numbers.",
            }
        )
    return JSONResponse(
        status_code = 422,
        content = {
            "status": "error",
            "code": "INVALID_INPUT",
            "message": "Please provide a valid input.",
            "data": {
                "invalid_fields": [err["loc"][-1] for err in errors]
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
app.include_router(
    files_router,
    prefix="/files"
)
app.include_router(
    admin_router,
    prefix="/admin",
    dependencies=[Depends(require_admin)]
)
app.include_router(
    docs_router,
    dependencies=[Depends(require_admin)]
)
app.include_router(
    feedback_router,
    prefix="/feedback"
)
