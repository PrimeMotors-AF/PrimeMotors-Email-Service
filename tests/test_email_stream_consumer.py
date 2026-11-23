import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException

from src.services.emailStreamConsumer import (
    CONSUMER_GROUP,
    DEAD_LETTER_STREAM,
    STREAM_NAME,
    _process_message,
)


class FakeResponse:
    status_code = 200

    def json(self):
        return {
            "event": "proposal.created",
            "data": {
                "proposal": {
                    "id": "proposal-1",
                    "offeredValue": "95000.00",
                    "message": "Tenho interesse.",
                    "status": "Pendente",
                    "createdAt": "2026-11-06T12:00:00",
                },
                "user": {
                    "id": "user-1",
                    "name": "Cliente",
                    "email": "cliente@example.com",
                },
                "car": {
                    "id": "car-1",
                    "name": "Modelo",
                    "value": "100000.00",
                },
            },
        }


class FakeHttpClient:
    def __init__(self, response):
        self.response = response
        self.get = AsyncMock(return_value=response)


class EmailStreamConsumerTests(unittest.IsolatedAsyncioTestCase):
    async def test_successful_delivery_acknowledges_stream_entry(self):
        redis = MagicMock()
        redis.exists = AsyncMock(return_value=0)
        redis.xack = AsyncMock()
        redis.delete = AsyncMock()
        http_client = FakeHttpClient(FakeResponse())
        fields = {
            "event": json.dumps(
                {
                    "eventId": "event-1",
                    "type": "proposal.created",
                    "occurredAt": "2026-11-06T12:00:00Z",
                    "proposalId": "proposal-1",
                }
            )
        }

        with (
            patch.dict("os.environ", {"SERVICE_TOKEN": "test-token"}),
            patch(
                "src.services.emailStreamConsumer.handle_proposal_created"
            ) as handle_proposal,
        ):
            await _process_message(
                redis,
                http_client,
                "123-0",
                fields,
            )

        http_client.get.assert_awaited_once()
        self.assertEqual(
            http_client.get.call_args.kwargs["headers"]["X-Service-Token"],
            "test-token",
        )
        handle_proposal.assert_called_once()
        redis.xack.assert_awaited_once_with(
            STREAM_NAME,
            CONSUMER_GROUP,
            "123-0",
        )
        redis.delete.assert_awaited_once()

    async def test_invalid_event_is_dead_lettered_and_acknowledged(self):
        redis = MagicMock()
        redis.exists = AsyncMock(return_value=0)
        redis.xadd = AsyncMock()
        redis.xack = AsyncMock()

        await _process_message(
            redis,
            FakeHttpClient(FakeResponse()),
            "123-1",
            {"event": "{invalid"},
        )

        self.assertEqual(redis.xadd.call_args.args[0], DEAD_LETTER_STREAM)
        self.assertEqual(
            redis.xadd.call_args.args[1]["reason"],
            "invalid_json",
        )
        redis.xack.assert_awaited_once_with(
            STREAM_NAME,
            CONSUMER_GROUP,
            "123-1",
        )

    async def test_rate_limit_failure_is_retried_without_acknowledging(self):
        redis = MagicMock()
        redis.exists = AsyncMock(return_value=0)
        redis.incr = AsyncMock(return_value=1)
        redis.expire = AsyncMock()
        redis.set = AsyncMock()
        redis.xack = AsyncMock()
        fields = {
            "event": json.dumps(
                {
                    "eventId": "event-1",
                    "type": "proposal.created",
                    "occurredAt": "2026-11-06T12:00:00Z",
                    "proposalId": "proposal-1",
                }
            )
        }

        with (
            patch.dict("os.environ", {"SERVICE_TOKEN": "test-token"}),
            patch(
                "src.services.emailStreamConsumer.handle_proposal_created",
                side_effect=HTTPException(
                    status_code=429,
                    headers={"Retry-After": "120"},
                ),
            ),
        ):
            await _process_message(
                redis,
                FakeHttpClient(FakeResponse()),
                "123-2",
                fields,
            )

        redis.set.assert_awaited_once_with(
            "email:retry-after:123-2",
            "1",
            ex=120,
        )
        redis.xack.assert_not_awaited()
