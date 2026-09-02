from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, Response, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import engine
from app.middleware.correlation import CorrelationMiddleware
from app.api.routes.auth import router as auth_router
from app.api.routes.morning_notes import router as morning_notes_router
from app.api.routes.feedback import router as feedback_router
from app.api.routes.pipeline import router as pipeline_router
from app.api.errors import (
    ApiError,
    ErrorCodes,
    PipelineError,
    build_dict_of_lists,
    json_response_from_api_error,
    translate,
)
from app.core.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.execute(text("SELECT 1"))
    yield
    await engine.dispose()


app = FastAPI(title="FinAgent", lifespan=lifespan)
logger = logging.getLogger(__name__)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOW_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["Authorization", "X-Pipeline-Run-Id", "X-Morning-Note-Id"],
)
app.add_middleware(CorrelationMiddleware)
app.include_router(auth_router)
app.include_router(morning_notes_router)
app.include_router(pipeline_router)
app.include_router(feedback_router)


@app.get("/health")
async def health(request: Request) -> Response:
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        return JSONResponse({"status": "ok", "db": "ok"})
    except SQLAlchemyError:
        api_error = ApiError(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code=ErrorCodes.SERVICE_UNAVAILABLE,
            message="Service degraded: database unreachable",
            details={"db": ["unreachable"]},
        )
        return json_response_from_api_error(api_error, request)


@app.exception_handler(ApiError)
async def api_error_handler(request, exc):
    return json_response_from_api_error(exc, request)


@app.exception_handler(Exception)
async def error_handler(request, exc):
    logger.exception("Unhandled error", extra={"url_path": request.url.path})
    api_error = ApiError(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        code=ErrorCodes.INTERNAL_ERROR,
        message="Internal server error"
    )
    return json_response_from_api_error(api_error, request)


@app.exception_handler(RequestValidationError)
async def validation_handler(request, exc: RequestValidationError) -> Response:
    details = build_dict_of_lists(exc.errors())
    api_error = ApiError(
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        ErrorCodes.VALIDATION_ERROR,
        "Validation error",
        details=details,
    )
    return json_response_from_api_error(api_error, request)


@app.exception_handler(PipelineError)
async def pipeline_error_handler(request, exc):
    api_error = translate(exc)
    return json_response_from_api_error(api_error, request)
