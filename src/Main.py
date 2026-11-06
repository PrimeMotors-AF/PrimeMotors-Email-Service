
import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from sqlalchemy import text

from src.database.connection import SessionLocal
from src.routes.emailRoutes import router as email_router
from src.services.emailStreamConsumer import run_email_stream_consumer


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not (os.getenv("EMAIL_REDIS_URL") or os.getenv("REDIS_URL")):
        raise RuntimeError("EMAIL_REDIS_URL ou REDIS_URL deve estar configurado.")
    if not os.getenv("SERVICE_TOKEN"):
        raise RuntimeError("SERVICE_TOKEN deve estar configurado.")
    claim_idle_ms = int(os.getenv("EMAIL_REDIS_CLAIM_IDLE_MS", "60000"))
    if claim_idle_ms <= 0:
        raise RuntimeError("EMAIL_REDIS_CLAIM_IDLE_MS deve ser positivo.")

    stop_event = asyncio.Event()
    consumer_task = asyncio.create_task(run_email_stream_consumer(stop_event))
    app.state.consumer_task = consumer_task
    try:
        yield
    finally:
        stop_event.set()
        await consumer_task

app = FastAPI(
    title="Prime Motors Email Service",
    description="Microserviço responsável pelo envio de e-mails do Prime Motors.",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(email_router)


@app.get("/health/ready")
async def readiness(request: Request):
    consumer_task = request.app.state.consumer_task
    if consumer_task.done():
        logger.error("Email stream consumer task is not running")
        return JSONResponse(
            status_code=503,
            content={"status": "consumer_unavailable"},
        )

    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        logger.exception("Email service database readiness check failed")
        return JSONResponse(
            status_code=503,
            content={"status": "unavailable"},
        )
    finally:
        db.close()

    redis_url = os.getenv("EMAIL_REDIS_URL") or os.getenv("REDIS_URL")
    redis = Redis.from_url(redis_url)
    try:
        await redis.ping()
    except Exception:
        logger.exception("Email service Redis readiness check failed")
        return JSONResponse(
            status_code=503,
            content={"status": "unavailable"},
        )
    finally:
        await redis.aclose()

    return {"status": "ready"}
