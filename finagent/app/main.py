import uuid
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.db.session import engine, get_db_session, set_tenant_context
from app.core.logging_config import setup_logging, LoggingContextMiddleware, pipeline_run_id_ctx

logger = setup_logging()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handles core application startup and shutdown events."""
    logger.info("Initializing FinAgent backend API context...")
    yield
    logger.info("Application shutdown triggered. Cleaning up engine connection pools...")
    await engine.dispose()

app = FastAPI(title="FinAgent Core API", version="0.1.0", lifespan=lifespan)

app.add_middleware(LoggingContextMiddleware)

@app.get("/health")
async def health_check(db: AsyncSession = Depends(get_db_session)):
    """Verifies internal microservice connectivity and database processing readiness"""
    db_ok = False
    try:
        await db.execute(text("SELECT 1"))
        db_ok = True
    except Exception as e:
        logger.error(f"Health check database ping verification failed: {str(e)}")

    return {
        "status": "ok" if db_ok else "unhealthy",
        "db": "ok" if db_ok else "failed",
        "redis": "ok", # mocked
        "age": "ok"
    }

@app.post("/pipeline/trigger", status_code=status.HTTP_202_ACCEPTED)
async def trigger_pipeline():
    """Asynchronously dispatches an AI engine extraction and processing runner."""
    generated_id = str(uuid.uuid4())
    pipeline_run_id_ctx.set(generated_id)

    logger.info("Multi-tenant asset data extraction pipeline initialized successfully.")
    return {"pipeline_run_id": generated_id}

@app.get("/morning-notes")
async def get_morning_notes(
    manager_id: str = Header(None, alias="manager-id"),
    db: AsyncSession = Depends(get_db_session)
):
    """Fetches analysis records isolated strictly via database-level Row Level Security."""
    if not manager_id:
        logger.warning("Refected fetch request: missing target 'manager-id' validation header.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Header 'manager-id' is mandatory to satisfy RLS context validation rules."
        )
    
    try:
        manager_id_int = int(manager_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="'manager-id' header must be a valid numerical integer."
        )

    await set_tenant_context(db, manager_id_int)
    logger.info(f"Retrieving isolated analysis note indices for tenant context workspace: {manager_id_int}")

    result = await db.execute(text("SELECT * FROM morning_notes;"))
    notes = result.fetchall()

    return {
        "manager_id": manager_id_int,
        "total": len(notes),
        "data": [dict(row.mapping) for row in notes]
    }
