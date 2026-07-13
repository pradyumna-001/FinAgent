import logging
import sys
from contextvars import ContextVar
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# request-scoped tracing context variables
pipeline_run_id_ctx: ContextVar[str] = ContextVar("pipeline_run_id", default="")
morning_note_id_ctx: ContextVar[str] = ContextVar("morning_note_id", default="")

class StructuredTracingFormatter(logging.Formatter):
    def format(self, record):
        p_id = pipeline_run_id_ctx.get()
        m_id = morning_note_id_ctx.get()

        ctx_tags = []
        if p_id: ctx_tags.append(f"pipeline_run_id={p_id}")
        if m_id: ctx_tags.append(f"morning_note_id={m_id}")

        if ctx_tags:
            record.msg = f"{record.msg} [{' '.join(ctx_tags)}]"
        return super().format(record)
    
def setup_logging():
    logger = logging.getLogger("finagent")
    logger.setLevel(logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    formatter = StructuredTracingFormatter("%(asctime)s - %(levelname)s - %(name)s - %(message)s")
    handler.setFormatter(formatter)

    logger.addHandler(handler)
    return logger

class LoggingContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        # pull tracking headers if they exist from incoming requests
        p_id = request.headers.get("X-Pipeline-Run-Id", "")
        m_id = request.headers.get("X-Morning-Note-Id", "")

        token_p = pipeline_run_id_ctx.set(p_id)
        token_m = pipeline_run_id_ctx.set(m_id)

        try:
            return await call_next(request)
        finally:
            pipeline_run_id_ctx.reset(token_p)
            pipeline_run_id_ctx.reset(token_m)
