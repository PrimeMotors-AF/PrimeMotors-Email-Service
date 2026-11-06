import unittest
from unittest.mock import MagicMock, patch

from redis.exceptions import RedisError

from src.services.emailIdempotencyService import (
    EmailIdempotencyUnavailable,
    EmailProcessingInProgress,
    LOCK_TTL_SECONDS,
    SUCCESS_TTL_SECONDS,
    cache_email_sent,
    email_was_sent,
    lock_proposal_email_processing,
)


class EmailIdempotencyServiceTests(unittest.TestCase):
    @patch.dict("os.environ", {"EMAIL_REDIS_URL": "redis://redis:6379"})
    @patch("src.services.emailIdempotencyService.Redis.from_url")
    def test_lock_uses_expiring_atomic_claim_and_releases_owned_lock(
        self,
        from_url,
    ):
        redis = MagicMock()
        redis.set.return_value = True
        from_url.return_value = redis

        with lock_proposal_email_processing("proposal-1") as cache:
            self.assertIs(cache, redis)

        lock_key = "email:proposal:proposal-1:lock"
        redis.set.assert_called_once()
        self.assertEqual(redis.set.call_args.args[0], lock_key)
        self.assertTrue(redis.set.call_args.kwargs["nx"])
        self.assertEqual(
            redis.set.call_args.kwargs["ex"],
            LOCK_TTL_SECONDS,
        )
        redis.eval.assert_called_once()
        self.assertEqual(redis.eval.call_args.args[2], lock_key)
        self.assertEqual(
            redis.eval.call_args.args[3],
            redis.set.call_args.args[1],
        )
        redis.close.assert_called_once()

    @patch.dict("os.environ", {"EMAIL_REDIS_URL": "redis://redis:6379"})
    @patch("src.services.emailIdempotencyService.Redis.from_url")
    def test_existing_lock_reports_processing_in_progress(self, from_url):
        redis = MagicMock()
        redis.set.return_value = None
        from_url.return_value = redis

        with self.assertRaises(EmailProcessingInProgress):
            with lock_proposal_email_processing("proposal-1"):
                self.fail("A busy proposal lock must not enter the handler.")

        redis.eval.assert_not_called()
        redis.close.assert_called_once()

    @patch.dict("os.environ", {"EMAIL_REDIS_URL": "redis://redis:6379"})
    @patch("src.services.emailIdempotencyService.Redis.from_url")
    def test_redis_failure_prevents_unprotected_processing(self, from_url):
        redis = MagicMock()
        redis.ping.side_effect = RedisError("Redis unavailable")
        from_url.return_value = redis

        with self.assertRaises(EmailIdempotencyUnavailable):
            with lock_proposal_email_processing("proposal-1"):
                self.fail("Processing must fail closed if Redis is unavailable.")

        redis.set.assert_not_called()
        redis.close.assert_called_once()

    def test_success_marker_uses_delivery_specific_key_and_ttl(self):
        redis = MagicMock()

        cache_email_sent(redis, "proposal-1", "customer")

        redis.set.assert_called_once_with(
            "email:proposal:proposal-1:customer:sent",
            "1",
            ex=SUCCESS_TTL_SECONDS,
        )

    def test_success_marker_is_checked_by_delivery_type(self):
        redis = MagicMock()
        redis.exists.return_value = 1

        self.assertTrue(email_was_sent(redis, "proposal-1", "internal"))
        redis.exists.assert_called_once_with(
            "email:proposal:proposal-1:internal:sent"
        )


if __name__ == "__main__":
    unittest.main()
