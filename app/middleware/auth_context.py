"""Middleware to extract manager_id from JWT token and store in request.state."""
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.security import decode_access_token


class AuthContextMiddleware(BaseHTTPMiddleware):
    """Middleware to extract manager_id from JWT token and store in request.state.

    Endpoints that need app.manager_id for RLS should read request.state.manager_id
    and set it on their own database session via SET LOCAL.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # Skip auth for health check and auth endpoints
        if request.url.path in ("/health", "/auth/login", "/auth/register", "/docs", "/openapi.json", "/redoc"):
            return await call_next(request)

        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            # No auth header - let the request proceed
            # The endpoint's auth dependency will handle 401 if needed
            return await call_next(request)

        token = auth_header.replace("Bearer ", "")

        try:
            payload = decode_access_token(token)
            manager_id = payload.get("manager_id")
            if manager_id:
                request.state.manager_id = manager_id
        except Exception:
            # Invalid token - let the endpoint's auth dependency handle the error
            pass

        return await call_next(request)
