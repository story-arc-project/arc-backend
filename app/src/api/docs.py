from fastapi import APIRouter
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from fastapi.requests import Request
from fastapi.responses import HTMLResponse, JSONResponse

docs_router = APIRouter()

@docs_router.get("/openapi.json", include_in_schema=False)
def openapi_schema(request: Request) -> JSONResponse:
    schema = get_openapi(
        title=request.app.title,
        version=request.app.version,
        routes=request.app.routes,
    )
    return JSONResponse(schema)

@docs_router.get("/docs", include_in_schema=False)
def swagger_docs() -> HTMLResponse:
    return get_swagger_ui_html(
        openapi_url="/openapi.json",
        title="docs",
    )