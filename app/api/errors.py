import logging
from datetime import datetime, UTC
from enum import StrEnum
from typing import Any, Optional, cast

from fastapi import HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field


class PipelineError(Exception):
    """Base for all pipeline-domain errors.

    Callers should catch this base for catch-all handling and discriminate on
    subclasses (e.g., MorningNoteNotFound) for retry or HTTP routing.
    """


class MorningNoteNotFound(PipelineError):
    """Raised when a morning note id does not resolve to a row"""


class InvalidTriggerPayload(PipelineError):
    """Raised when the trigger request fails semantic validation beyond 
    pydantic's structural checks (e.g., company_id not in manager's book).
    """


class InvalidTokenError(Exception):
    def __init__(self, message: str = "Invalid or expired token"):
        self.message = message
        super().__init__(self.message)


class ErrorCodes(StrEnum):
    MISSING_HEADER = "MISSING_HEADER"
    INVALID_HEADER = "INVALID_HEADER"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    RLS_VIOLATION = "RLS_VIOLATION"
    CONFLICT = "CONFLICT"
    IDEMPOTENCY_KEY_EXISTS = "IDEMPOTENCY_KEY_EXISTS"
    UNAUTHORIZED = "UNAUTHORIZED"
    NO_ACTIVE_RUN = "NO_ACTIVE_RUN"
    INVALID_TRIGGER_PAYLOAD = "INVALID_TRIGGER_PAYLOAD"

    INTERNAL_ERROR = "INTERNAL_ERROR"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    EXTERNAL_API_ERROR = "EXTERNAL_API_ERROR"
    DATABASE_ERROR = "DATABASE_ERROR"


class ApiErrorDetail(BaseModel):
    code: str
    message: str
    details: Optional[dict[str, list[str]]] = None
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    path: Optional[str] = None


class ApiError(HTTPException):
    def __init__(self, status_code: int, code: str, message: str, details: Optional[dict[str, list[str]]] = None, path: Optional[str] = None):
        self.status_code = status_code
        self.detail = cast(Any, ApiErrorDetail(code=code, message=message, details=details, path=path))


logger = logging.getLogger(__name__)


def json_response_from_api_error(api_error: ApiError, request) -> JSONResponse:
    detail = cast(ApiErrorDetail, api_error.detail)
    payload = detail.model_dump()
    if payload.get("path") is None:
        payload["path"] = request.url.path
    return JSONResponse(
        content=payload,
        status_code=api_error.status_code
    )


def build_dict_of_lists(errors) -> dict[str, list[str]]:
    details: dict[str, list[str]] = {}
    for err in errors:
        loc = err.get("loc", ())
        field = loc[-1] if loc else "_root"
        msg = err["msg"]
        if field not in details:
            details[field] = []
        details[field].append(msg)

    return details


_ERROR_MAP: dict[type[PipelineError], tuple[int, ErrorCodes, str]] = {
    MorningNoteNotFound: (
        status.HTTP_404_NOT_FOUND, ErrorCodes.NO_ACTIVE_RUN,
        "Morning note not found in current stream.",
    ),
    InvalidTriggerPayload: (
        status.HTTP_422_UNPROCESSABLE_CONTENT, ErrorCodes.INVALID_TRIGGER_PAYLOAD,
        "Payload well-formed but breaks logic",
    ),
}


def _build_api_error(status_code: int, code: ErrorCodes, message: str) -> ApiError:
    return ApiError(status_code=status_code, code=code, message=message)


def translate(exc: PipelineError) -> ApiError:
    spec = _ERROR_MAP.get(type(exc))
    if spec is not None:
        status_code, code, message = spec
        return _build_api_error(status_code, code, message)

    logger.exception(
        "Unmapped PipelineError subclass escaped to HTTP boundary",
        extra={
            "exc_type": type(exc).__name__,
            "exc_args": exc.args,
        },
    )

    return _build_api_error(
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        ErrorCodes.INTERNAL_ERROR,
        "Internal server error",
    )
