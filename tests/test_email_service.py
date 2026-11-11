import os
import unittest
from unittest.mock import patch

from fastapi import HTTPException, Response

from src.models.emailModel import (
    CarModel,
    ProposalCreatedDataModel,
    ProposalCreatedModel,
    ProposalModel,
    UserModel,
)
from src.services.emailService import (
    send_customer_proposal_email,
    send_internal_proposal_notification,
)
from src.routes.emailRoutes import proposal_created

SMTP_ENV = {
    "SMTP_HOST": "smtp.example.com",
    "SMTP_PORT": "587",
    "SMTP_USER": "mailer@example.com",
    "SMTP_PASSWORD": "test-password",
    "SMTP_FROM": "mailer@example.com",
}


def create_proposal_event() -> ProposalCreatedModel:
    return ProposalCreatedModel(
        event="proposal.created",
        data=ProposalCreatedDataModel(
            proposal=ProposalModel(
                id="proposal-1",
                offeredValue="100000.00",
                message="Gostaria de negociar.",
                status="Pendente",
                createdAt="2026-11-11T17:51:00Z",
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


def get_parts(message):
    text = message.get_body(preferencelist=("plain",)).get_content()
    html = message.get_body(preferencelist=("html",)).get_content()
    return text, html


class ProposalEmailServiceTests(unittest.TestCase):
    @patch.dict(os.environ, {"SERVICE_TOKEN": "unit-test-secret"})
    def test_request_with_invalid_service_token_is_rejected(self):
        with self.assertRaises(HTTPException) as error:
            proposal_created(
                create_proposal_event(),
                Response(),
                "invalid-token",
            )

        self.assertEqual(error.exception.status_code, 401)

    @patch.dict(os.environ, SMTP_ENV)
    @patch("src.services.emailService.smtplib.SMTP")
    def test_customer_confirmation_uses_registered_email(self, smtp_class):
        smtp = smtp_class.return_value.__enter__.return_value

        send_customer_proposal_email(
            create_proposal_event(),
            "cliente@example.com",
        )

        message = smtp.send_message.call_args.args[0]
        self.assertEqual(message["To"], "cliente@example.com")
        self.assertEqual(message["Subject"], "Recebemos sua proposta | Prime Motors")
        self.assertNotIn("Cc", message)

        text, html = get_parts(message)
        self.assertIn("Prezado(a) Cliente", text)
        self.assertIn("RESUMO DA PROPOSTA", text)
        self.assertIn("PRÓXIMOS PASSOS", text)
        self.assertIn("Protocolo: proposal-1", text)
        self.assertIn("Valor anunciado: R$ 110.000,00", text)
        self.assertIn("Valor ofertado: R$ 100.000,00", text)
        self.assertIn("R$ 10.000,00 abaixo do valor anunciado (9,09%)", text)
        self.assertIn("Data de envio: 11/11/2026 às 14:51", text)
        self.assertIn("Agradecemos pelo seu", text)
        self.assertIn("RESUMO DA PROPOSTA", html)
        self.assertIn("R$ 100.000,00", html)

    @patch.dict(os.environ, SMTP_ENV)
    @patch("src.services.emailService.smtplib.SMTP")
    def test_internal_notification_uses_configured_recipient(self, smtp_class):
        smtp = smtp_class.return_value.__enter__.return_value

        send_internal_proposal_notification(
            create_proposal_event(),
            "equipe@example.com",
        )

        message = smtp.send_message.call_args.args[0]
        self.assertEqual(message["To"], "equipe@example.com")
        self.assertEqual(message["Subject"], "Nova proposta recebida | Prime Motors")
        self.assertNotIn("Cc", message)

        text, html = get_parts(message)
        self.assertIn("cliente@example.com", text)
        self.assertIn("DADOS DA PROPOSTA", text)
        self.assertIn("DADOS DO CLIENTE", text)
        self.assertIn("MENSAGEM DO CLIENTE", text)
        self.assertIn("AÇÃO NECESSÁRIA", text)
        self.assertIn("Data de envio: 11/11/2026 às 14:51", text)
        self.assertIn("Valor ofertado: R$ 100.000,00", text)
        self.assertIn("cliente@example.com", html)


if __name__ == "__main__":
    unittest.main()