import logging
import os
import uuid
from contextlib import contextmanager
from typing import Iterator

from redis import Redis
from redis.exceptions import RedisError


logger = logging.getLogger(__name__)

LOCK_TTL_SECONDS = 120
SUCCESS_TTL_SECONDS = 35 * 24 * 60 * 60

_RELEASE_LOCK_SCRIPT = """
if redis.call("GET", KEYS[1]) == ARGV[1] then
    return redis.call("DEL", KEYS[1])
end
return 0
"""


class EmailProcessingInProgress(Exception):
    pass


class EmailIdempotencyUnavailable(Exception):
    pass


def _redis_client() -> Redis:
    redis_url = os.getenv("EMAIL_REDIS_URL") or os.getenv("REDIS_URL")
    if not redis_url:
        raise EmailIdempotencyUnavailable(
            "EMAIL_REDIS_URL ou REDIS_URL deve estar configurado."
        )
    return Redis.from_url(
        redis_url,
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5,
    )


def _lock_key(proposal_id: str) -> str:
    return f"email:proposal:{proposal_id}:lock"


def _success_key(proposal_id: str, delivery_type: str) -> str:
    return f"email:proposal:{proposal_id}:{delivery_type}:sent"


@contextmanager
def lock_proposal_email_processing(proposal_id: str) -> Iterator[Redis]:
    redis = _redis_client()
    token = uuid.uuid4().hex
    lock_key = _lock_key(proposal_id)
    acquired = False

    try:
        try:
            redis.ping()
            acquired = bool(
                redis.set(
                    lock_key,
                    token,
                    nx=True,
                    ex=LOCK_TTL_SECONDS,
                )
            )
        except RedisError as error:
            raise EmailIdempotencyUnavailable(
                "Não foi possível acessar o Redis para proteger o envio."
            ) from error

        if not acquired:
            raise EmailProcessingInProgress(proposal_id)

        yield redis
    finally:
        if acquired:
            try:
                redis.eval(_RELEASE_LOCK_SCRIPT, 1, lock_key, token)
            except RedisError:
                logger.exception(
                    "Could not release proposal email lock; it will expire by TTL",
                    extra={"proposal_id": proposal_id},
                )
        redis.close()


def email_was_sent(
    redis: Redis,
    proposal_id: str,
    delivery_type: str,
) -> bool:
    try:
        return bool(redis.exists(_success_key(proposal_id, delivery_type)))
    except RedisError as error:
        raise EmailIdempotencyUnavailable(
            "Não foi possível verificar o status do envio no Redis."
        ) from error


def cache_email_sent(
    redis: Redis,
    proposal_id: str,
    delivery_type: str,
) -> None:
    try:
        redis.set(
            _success_key(proposal_id, delivery_type),
            "1",
            ex=SUCCESS_TTL_SECONDS,
        )
    except RedisError:
        logger.exception(
            "Could not cache email delivery; the database remains authoritative",
            extra={"proposal_id": proposal_id, "delivery_type": delivery_type},
        )
