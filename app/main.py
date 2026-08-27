from contextlib import asynccontextmanager
import logging
from typing import cast

from fastapi import FastAPI, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import engine
from app.middleware.correlation import CorrelationMiddleware
from app.api.routes.auth import router as auth_router
from app.api.routes.morning_notes import router as morning_notes_router
from app.api.routes.feedback import router as feedback_router
from app.api.routes.pipeline import router as pipeline_router
from app.api.errors import ApiError, ApiErrorDetail, ErrorCodes, MorningNoteNotFound


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.execute(text("SELECT 1"))
    yield
    await engine.dispose()


app = FastAPI(title="FinAgent", lifespan=lifespan)
logger = logging.getLogger(__name__)


app.add_middleware(CorrelationMiddleware)
app.include_router(auth_router)
app.include_router(morning_notes_router)
app.include_router(pipeline_router)
app.include_router(feedback_router)


@app.get("/health")
async def health() -> JSONResponse:
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        return JSONResponse({"status": "ok", "db": "ok"})
    except SQLAlchemyError:
        return JSONResponse({"status": "degraded", "db": "unreachable"}, status_code=503)


@app.exception_handler(MorningNoteNotFound)
async def morning_note_not_found_handler(request, exc):
    # TODO(#19): re-evaluate log level when this becomes a polling hot path
    return JSONResponse(
        status_code=404,
        content={"detail": f"morning note {exc.args[0]!r} not found"}
    )


@app.exception_handler(ApiError)
async def api_error_handler(request, exc):
    detail = cast(ApiErrorDetail, exc.detail)
    detail.path = request.url.path

    return JSONResponse(
        content=detail.model_dump(),
        status_code=exc.status_code
    )


@app.exception_handler(Exception)
async def error_handler(request, exc):
    logger.exception("Unhandled error", extra={"url_path": request.url.path})
    api_error = ApiError(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        code=ErrorCodes.INTERNAL_ERROR,
        message="Internal server error"
    )
    detail = cast(ApiErrorDetail, api_error.detail)
    detail.path = request.url.path

    return JSONResponse(
        content=detail.model_dump(),
        status_code=api_error.status_code
    )


def _build_dict_of_lists(errors):
    details: dict[str, list[str]] = {}
    for err in errors:
        loc = err["loc"]
        field = loc[-1]
        msg = err["msg"]
        if field not in details:
            details[field] = []
        details[field].append(msg)

    return details


@app.exception_handler(RequestValidationError)
async def validation_handler(request, exc: RequestValidationError) -> Response:
    details = _build_dict_of_lists(exc.errors)
    api_error = ApiError(422, ErrorCodes.VALIDATION_ERROR, "Validation error", details=details)
    detail = cast(ApiErrorDetail, api_error.detail)
    detail.path = request.url.path

    return JSONResponse(
        content=detail.model_dump(),
        status_code=api_error.status_code
    )
