import hashlib
import os
import time
from dataclasses import dataclass

from sqlalchemy.dialects.mysql import insert
from sqlalchemy.orm import Session

from src.models.emailRateLimitModel import EmailRateLimit


@dataclass(frozen=True)
class EmailRateLimitReservation:
    limit: int
    remaining: int
    reset: int
    window_seconds: int


class EmailRateLimitExceeded(Exception):
    def __init__(self, retry_after: int, limit: int, window_seconds: int):
        self.retry_after = retry_after
        self.limit = limit
        self.window_seconds = window_seconds
        super().__init__("Limite de envio de e-mails excedido.")


def _positive_setting(name: str, default: int) -> int:
    value = int(os.getenv(name, str(default)))
    if value <= 0:
        raise RuntimeError(f"{name} deve ser um inteiro positivo.")
    return value


def reserve_email_sends(
    db: Session,
    customer_email: str | None,
    message_count: int,
) -> EmailRateLimitReservation:
    if message_count <= 0:
        raise ValueError("message_count deve ser positivo.")

    window_seconds = _positive_setting("EMAIL_RATE_LIMIT_WINDOW_SECONDS", 3600)
    recipient_limit = _positive_setting("EMAIL_RATE_LIMIT_PER_RECIPIENT", 5)
    global_limit = _positive_setting("EMAIL_RATE_LIMIT_GLOBAL", 100)

    now = int(time.time())
    window_start = now // window_seconds * window_seconds
    reservations: dict[str, tuple[int, int]] = {}

    if customer_email:
        normalized_email = customer_email.strip().lower()
        recipient_key = hashlib.sha256(
            f"recipient:{normalized_email}".encode("utf-8")
        ).hexdigest()
        reservations[recipient_key] = (1, recipient_limit)

    global_key = hashlib.sha256(b"global").hexdigest()
    reservations[global_key] = (message_count, global_limit)

    statement = insert(EmailRateLimit).values(
        [
            {
                "key_hash": key_hash,
                "window_start": window_start,
                "attempts": 0,
            }
            for key_hash in sorted(reservations)
        ]
    )
    db.execute(
        statement.on_duplicate_key_update(
            key_hash=statement.inserted.key_hash
        )
    )

    global_attempts = None
    for key_hash in sorted(reservations):
        rate_limit = (
            db.query(EmailRateLimit)
            .filter(EmailRateLimit.key_hash == key_hash)
            .with_for_update()
            .one()
        )
        if rate_limit.window_start != window_start:
            rate_limit.window_start = window_start
            rate_limit.attempts = 0

        increment, maximum = reservations[key_hash]
        if rate_limit.attempts + increment > maximum:
            retry_after = max(
                1,
                rate_limit.window_start + window_seconds - now,
            )
            raise EmailRateLimitExceeded(
                retry_after,
                maximum,
                window_seconds,
            )
        rate_limit.attempts += increment
        if key_hash == global_key:
            global_attempts = rate_limit.attempts

    db.commit()
    if global_attempts is None:
        raise RuntimeError("Não foi possível registrar o limite global de e-mails.")

    return EmailRateLimitReservation(
        limit=global_limit,
        remaining=max(0, global_limit - global_attempts),
        reset=max(1, window_start + window_seconds - now),
        window_seconds=window_seconds,
    )
