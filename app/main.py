from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from app.db.session import engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.execute(text("SELECT 1"))
    yield
    await engine.dispose()


app = FastAPI(title="FinAgent", lifespan=lifespan)


@app.get("/health")
async def health() -> JSONResponse:
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        return JSONResponse({"status": "ok", "db": "ok"})
    except SQLAlchemyError:
        return JSONResponse({"status": "degraded", "db": "unreachable"}, status_code=503)
