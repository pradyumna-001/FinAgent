from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from app.core.context import current_morning_note_id, current_pipeline_run_id


class CorrelationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        pipeline = request.headers.get("X-Pipeline-Run_Id")
        note = request.headers.get("X-Morning-Note-Id")
        p_token = current_pipeline_run_id.set(pipeline) if pipeline else None
        n_token = current_morning_note_id.set(note) if note else None
        
        try:
            return await call_next(request)
        finally:
            if p_token:
                current_pipeline_run_id.reset(p_token)
            if n_token:
                current_morning_note_id.reset(n_token)
