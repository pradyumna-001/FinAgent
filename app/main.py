from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import engine
from app.middleware.correlation import CorrelationMiddleware
from app.api.routes.auth import router as auth_router
from app.api.routes.morning_notes import router as morning_notes_router
from app.api.routes.feedback import router as feedback_router
from app.api.routes.pipeline import router as pipeline_router
from app.api.errors import MorningNoteNotFound


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.execute(text("SELECT 1"))
    yield
    await engine.dispose()


app = FastAPI(title="FinAgent", lifespan=lifespan)


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
