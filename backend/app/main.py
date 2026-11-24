"""FastAPI application: routers, CORS, rate limiting, error handlers, startup recovery."""

import logging
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text

from app.config import get_settings
from app.db import SessionLocal
from app.ingestion.pipeline import recover_stuck_documents
from app.logging_setup import request_id_var, setup_logging
from app.ratelimit import limiter
from app.routers import auth, chat, documents
from app.schemas import HealthOut

settings = get_settings()
setup_logging()
logger = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    if settings.APP_ENV != "test":
        try:
            await recover_stuck_documents()
        except Exception:  # noqa: BLE001 - never block startup
            logger.exception("startup recovery failed")
        await _check_llm_models()
    yield


async def _check_llm_models() -> None:
    """Log whether the configured Gemini chat model exists, and which Flash models do."""
    if settings.LLM_PROVIDER != "gemini" or not settings.GEMINI_API_KEY:
        return
    try:
        from app.llm import get_provider

        provider = get_provider()
        names = await provider.available_chat_models()  # type: ignore[attr-defined]
        flash = sorted(n for n in names if "flash" in n)
        level = logging.INFO if settings.GEMINI_CHAT_MODEL in names else logging.ERROR
        logger.log(
            level,
            "configured chat model %s available=%s; flash models: %s",
            settings.GEMINI_CHAT_MODEL,
            settings.GEMINI_CHAT_MODEL in names,
            ", ".join(flash),
        )
    except Exception:  # noqa: BLE001 - diagnostics only
        logger.warning("could not list Gemini models", exc_info=True)


app = FastAPI(
    title="Hyundai Assistant API",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    redoc_url=None,
)
app.state.limiter = limiter

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.FRONTEND_ORIGIN.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_context(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    token = request_id_var.set(rid)
    start = time.perf_counter()
    try:
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        if request.url.path != "/api/health":
            logger.info(
                "%s %s -> %s (%.0f ms)",
                request.method,
                request.url.path,
                response.status_code,
                (time.perf_counter() - start) * 1000,
            )
        return response
    finally:
        request_id_var.reset(token)


@app.exception_handler(RateLimitExceeded)
async def rate_limited(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse({"detail": "Too many attempts. Please wait a minute and try again."}, status_code=429)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = exc.errors()
    first = errors[0] if errors else {}
    msg = str(first.get("msg", "Invalid request")).removeprefix("Value error, ")
    field = ".".join(str(p) for p in first.get("loc", []) if p not in ("body", "query", "path"))
    return JSONResponse(
        {
            "detail": f"{field}: {msg}" if field else msg,
            "errors": [{"loc": e.get("loc"), "msg": e.get("msg")} for e in errors],
        },
        status_code=422,
    )


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=exc.headers)


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse({"detail": "Something went wrong. Please try again."}, status_code=500)


@app.get("/api/health", response_model=HealthOut, response_model_exclude_none=True, tags=["health"])
async def health() -> HealthOut | JSONResponse:
    try:
        async with SessionLocal() as s:
            await s.execute(text("SELECT 1"))
        return HealthOut(status="ok", db=True)
    except Exception:  # noqa: BLE001
        logger.exception("health check DB failure")
        return JSONResponse({"status": "degraded", "db": False}, status_code=503)


app.include_router(auth.router, prefix="/api")
app.include_router(documents.router, prefix="/api")
app.include_router(chat.router, prefix="/api")
