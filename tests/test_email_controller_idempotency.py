import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi import HTTPException, Response

from src.models.emailModel import (
    CarModel,
    ProposalCreatedDataModel,
    ProposalCreatedModel,
    ProposalModel,
    UserModel,
)
from src.services.emailIdempotencyService import EmailProcessingInProgress
from src.controllers.emailController import (
    _process_proposal_created,
    handle_proposal_created,
)


def create_proposal_event() -> ProposalCreatedModel:
    return ProposalCreatedModel(
        event="proposal.created",
        data=ProposalCreatedDataModel(
            proposal=ProposalModel(
                id="proposal-1",
                offeredValue="100000.00",
                message="Gostaria de negociar.",
                status="Pendente",
                createdAt="2026-11-06T12:00:00",
            ),
            user=UserModel(
                id="user-1",
                name="Cliente",
                email="cliente@example.com",
            ),
            car=CarModel(
                id="car-1",
                name="Carro",
                value="110000.00",
            ),
        ),
    )


class EmailControllerIdempotencyTests(unittest.TestCase):
    def test_lock_contention_is_returned_as_retryable_http_error(self):
        with patch(
            "src.controllers.emailController.lock_proposal_email_processing",
            side_effect=EmailProcessingInProgress("proposal-1"),
        ):
            with self.assertRaises(HTTPException) as error:
                handle_proposal_created(create_proposal_event(), Response())

        self.assertEqual(error.exception.status_code, 503)
        self.assertEqual(error.exception.headers["Retry-After"], "5")

    def test_cached_success_reconciles_database_without_resending(self):
        proposal = SimpleNamespace(
            proposal_id="proposal-1",
            user_email="cliente@example.com",
            customer_email_sent=False,
            notification_email_sent=False,
        )
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = proposal
        redis = MagicMock()

        with (
            patch(
                "src.controllers.emailController.SessionLocal",
                return_value=db,
            ),
            patch(
                "src.controllers.emailController.email_was_sent",
                return_value=True,
            ),
            patch(
                "src.controllers.emailController.send_customer_proposal_email"
            ) as send_customer,
            patch(
                "src.controllers.emailController.send_internal_proposal_notification"
            ) as send_internal,
        ):
            result = _process_proposal_created(
                create_proposal_event(),
                Response(),
                redis,
            )

        self.assertEqual(result["message"], "Proposta já recebida anteriormente.")
        self.assertTrue(proposal.customer_email_sent)
        self.assertTrue(proposal.notification_email_sent)
        self.assertEqual(db.commit.call_count, 1)
        send_customer.assert_not_called()
        send_internal.assert_not_called()


if __name__ == "__main__":
    unittest.main()
