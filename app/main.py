from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.chat import router as chat_router
from app.api.mock_integrations import router as integrations_router
from app.config import load_settings
from app.runtime import Runtime, build_runtime


def _error_response(request: Request, status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {"code": code, "message": message},
            "request_id": getattr(request.state, "request_id", str(uuid4())),
        },
    )


def create_app(runtime: Runtime | None = None) -> FastAPI:
    application = FastAPI(title="Meeting Assistant", docs_url=None, redoc_url=None)
    application.state.runtime = runtime or build_runtime(settings=load_settings())

    @application.middleware("http")
    async def attach_request_id(request: Request, call_next):
        request.state.request_id = request.headers.get("X-Request-ID") or str(uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    @application.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError) -> JSONResponse:
        del exc
        return _error_response(request, 422, "invalid_request", "Request validation failed.")

    @application.exception_handler(Exception)
    async def internal_error(request: Request, exc: Exception) -> JSONResponse:
        del exc
        return _error_response(
            request, 500, "internal_error", "The service could not process this request."
        )

    @application.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        detail = (
            exc.detail
            if isinstance(exc.detail, dict)
            else {"code": "request_failed", "message": str(exc.detail)}
        )
        return _error_response(request, exc.status_code, detail["code"], detail["message"])

    @application.get("/health")
    async def health() -> dict[str, bool]:
        return {"ok": True}

    application.include_router(chat_router)
    application.include_router(integrations_router)
    application.mount(
        "/",
        StaticFiles(directory=Path(__file__).parent / "static", html=True),
        name="static",
    )
    return application


app = create_app()
