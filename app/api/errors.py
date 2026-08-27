from datetime import datetime, UTC
from enum import StrEnum
from typing import Any, Optional, cast

from fastapi import HTTPException
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
