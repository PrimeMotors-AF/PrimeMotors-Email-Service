import asyncio
import json
import logging
import os
import socket
import uuid
from urllib.parse import quote

import httpx
from fastapi import HTTPException, Response
from pydantic import ValidationError
from redis.asyncio import Redis
from redis.exceptions import RedisError, ResponseError

from src.controllers.emailController import handle_proposal_created
from src.models.emailModel import ProposalCreatedModel


logger = logging.getLogger(__name__)

STREAM_NAME = "email.confirmations"
DEAD_LETTER_STREAM = "email.confirmations.dead"
CONSUMER_GROUP = "email-service"
STREAM_MAX_LENGTH = 10_000
MESSAGE_BATCH_SIZE = 10
BACKEND_REQUEST_TIMEOUT_SECONDS = 10
RETRY_DELAY_SECONDS = 60
MAX_RETRY_DELAY_SECONDS = 3600


def _positive_setting(name: str, default: int) -> int:
    value = int(os.getenv(name, str(default)))
    if value <= 0:
        raise RuntimeError(f"{name} deve ser um inteiro positivo.")
    return value


def _consumer_name() -> str:
    return f"{socket.gethostname()}-{uuid.uuid4().hex[:12]}"


async def _move_to_dead_letter(
    redis: Redis,
    stream_id: str,
    fields: dict[str, str],
    reason: str,
) -> None:
    await redis.xadd(
        DEAD_LETTER_STREAM,
        {
            "source_stream_id": stream_id,
            "event": fields.get("event", ""),
            "reason": reason,
        },
        maxlen=STREAM_MAX_LENGTH,
        approximate=True,
    )
    await redis.xack(STREAM_NAME, CONSUMER_GROUP, stream_id)
    logger.error(
        "Email stream event moved to dead-letter stream",
        extra={"stream_id": stream_id, "reason": reason},
    )


def _is_permanent_http_error(status_code: int) -> bool:
    return status_code in (400, 404, 409, 422)


async def _schedule_retry(
    redis: Redis,
    stream_id: str,
    retry_after: int | None = None,
) -> None:
    if retry_after is None:
        attempts_key = f"email:retry-count:{stream_id}"
        attempts = await redis.incr(attempts_key)
        await redis.expire(attempts_key, 24 * 60 * 60)
        retry_after = min(
            RETRY_DELAY_SECONDS * (2 ** min(attempts - 1, 6)),
            MAX_RETRY_DELAY_SECONDS,
        )

    await redis.set(
        f"email:retry-after:{stream_id}",
        "1",
        ex=max(1, retry_after),
    )


async def _process_message(
    redis: Redis,
    http_client: httpx.AsyncClient,
    stream_id: str,
    fields: dict[str, str],
) -> None:
    retry_key = f"email:retry-after:{stream_id}"
    if await redis.exists(retry_key):
        return

    raw_event = fields.get("event")
    if not raw_event:
        await _move_to_dead_letter(redis, stream_id, fields, "missing_event")
        return

    try:
        event = json.loads(raw_event)
    except json.JSONDecodeError:
        await _move_to_dead_letter(redis, stream_id, fields, "invalid_json")
        return

    if (
        not isinstance(event, dict)
        or event.get("type") != "proposal.created"
        or not isinstance(event.get("eventId"), str)
        or not event["eventId"]
        or not isinstance(event.get("proposalId"), str)
        or not event["proposalId"]
    ):
        await _move_to_dead_letter(redis, stream_id, fields, "invalid_event")
        return

    backend_url = os.getenv("BACKEND_API_URL", "http://backend:3000").rstrip("/")
    service_token = os.getenv("SERVICE_TOKEN")
    if not service_token:
        raise RuntimeError("SERVICE_TOKEN não está configurado.")

    try:
        response = await http_client.get(
            (
                f"{backend_url}/internal/proposals/"
                f"{quote(event['proposalId'], safe='')}/email-event"
            ),
            headers={"X-Service-Token": service_token},
        )
    except httpx.HTTPError as error:
        await _schedule_retry(redis, stream_id)
        logger.warning(
            "Backend lookup for email event failed; retry scheduled",
            extra={"stream_id": stream_id, "error_type": type(error).__name__},
        )
        return

    if _is_permanent_http_error(response.status_code):
        await _move_to_dead_letter(
            redis,
            stream_id,
            fields,
            f"backend_http_{response.status_code}",
        )
        return

    if response.status_code < 200 or response.status_code >= 300:
        await _schedule_retry(redis, stream_id)
        logger.warning(
            "Backend returned an error for email event; retry scheduled",
            extra={"stream_id": stream_id, "status_code": response.status_code},
        )
        return

    try:
        payload = response.json()
        if payload["data"]["proposal"]["id"] != event["proposalId"]:
            await _move_to_dead_letter(
                redis,
                stream_id,
                fields,
                "proposal_id_mismatch",
            )
            return
        email_event = ProposalCreatedModel.model_validate(payload)
    except (ValueError, KeyError, TypeError, ValidationError):
        await _move_to_dead_letter(
            redis,
            stream_id,
            fields,
            "invalid_backend_payload",
        )
        return

    try:
        await asyncio.to_thread(
            handle_proposal_created,
            email_event,
            Response(),
        )
    except HTTPException as error:
        if _is_permanent_http_error(error.status_code):
            await _move_to_dead_letter(
                redis,
                stream_id,
                fields,
                f"email_http_{error.status_code}",
            )
            return

        retry_header = (error.headers or {}).get("Retry-After")
        retry_after = None
        if retry_header:
            try:
                retry_after = min(
                    max(1, int(retry_header)),
                    MAX_RETRY_DELAY_SECONDS,
                )
            except ValueError:
                retry_after = None

        await _schedule_retry(redis, stream_id, retry_after)
        logger.warning(
            "Email API processing failed; retry scheduled",
            extra={"stream_id": stream_id, "status_code": error.status_code},
        )
        return
    except Exception as error:
        await _schedule_retry(redis, stream_id)
        logger.exception(
            "Email event processing failed; retry scheduled",
            extra={"stream_id": stream_id, "error_type": type(error).__name__},
        )
        return

    await redis.xack(STREAM_NAME, CONSUMER_GROUP, stream_id)
    await redis.delete(
        retry_key,
        f"email:retry-count:{stream_id}",
    )
    logger.info(
        "Email stream event processed",
        extra={"stream_id": stream_id, "event_id": event.get("eventId")},
    )


async def _ensure_consumer_group(redis: Redis) -> None:
    try:
        await redis.xgroup_create(
            STREAM_NAME,
            CONSUMER_GROUP,
            id="0-0",
            mkstream=True,
        )
    except ResponseError as error:
        if "BUSYGROUP" not in str(error):
            raise


async def run_email_stream_consumer(stop_event: asyncio.Event) -> None:
    redis_url = os.getenv("EMAIL_REDIS_URL") or os.getenv("REDIS_URL")
    if not redis_url:
        raise RuntimeError("EMAIL_REDIS_URL ou REDIS_URL deve estar configurado.")

    consumer_name = _consumer_name()
    claim_idle_ms = _positive_setting("EMAIL_REDIS_CLAIM_IDLE_MS", 60_000)
    redis = Redis.from_url(redis_url, decode_responses=True)

    try:
        while not stop_event.is_set():
            try:
                await redis.ping()
                await _ensure_consumer_group(redis)
                break
            except RedisError:
                logger.exception("Redis unavailable while starting email consumer")
                await asyncio.sleep(5)

        if stop_event.is_set():
            return

        logger.info(
            "Email Redis Stream consumer started",
            extra={
                "stream": STREAM_NAME,
                "group": CONSUMER_GROUP,
                "consumer": consumer_name,
            },
        )

        async with httpx.AsyncClient(
            timeout=BACKEND_REQUEST_TIMEOUT_SECONDS
        ) as http_client:
            claim_cursor = "0-0"
            while not stop_event.is_set():
                try:
                    claim_result = await redis.xautoclaim(
                        STREAM_NAME,
                        CONSUMER_GROUP,
                        consumer_name,
                        min_idle_time=claim_idle_ms,
                        start_id=claim_cursor,
                        count=MESSAGE_BATCH_SIZE,
                    )
                    claim_cursor = claim_result[0]
                    pending_messages = claim_result[1]
                    for stream_id, fields in pending_messages:
                        await _process_message(
                            redis,
                            http_client,
                            stream_id,
                            fields,
                        )

                    if pending_messages:
                        continue

                    new_messages = await redis.xreadgroup(
                        CONSUMER_GROUP,
                        consumer_name,
                        {STREAM_NAME: ">"},
                        count=MESSAGE_BATCH_SIZE,
                        block=1_000,
                    )
                    for _, messages in new_messages:
                        for stream_id, fields in messages:
                            await _process_message(
                                redis,
                                http_client,
                                stream_id,
                                fields,
                            )
                except RedisError:
                    logger.exception("Redis error in email stream consumer")
                    await asyncio.sleep(5)
                except Exception:
                    logger.exception("Unexpected error in email stream consumer")
                    await asyncio.sleep(5)
    finally:
        await redis.aclose()
        logger.info(
            "Email Redis Stream consumer stopped",
            extra={"consumer": consumer_name},
        )
