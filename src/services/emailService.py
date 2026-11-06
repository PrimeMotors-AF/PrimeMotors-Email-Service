
from datetime import datetime
from decimal import Decimal
import os
import smtplib
from email.message import EmailMessage

from src.models.emailModel import ProposalCreatedModel


def _format_brl(value: Decimal) -> str:
    formatted_value = f"{value:,.2f}"
    localized_value = formatted_value.replace(",", "_").replace(".", ",")
    return f"R$ {localized_value.replace('_', '.')}"


def _format_proposal_date(value: datetime) -> str:
    return value.strftime("%d/%m/%Y às %H:%M")


def get_proposal_notification_email() -> str:
    recipient_email = os.getenv("PROPOSAL_NOTIFICATION_EMAIL")
    if not recipient_email:
        raise RuntimeError(
            "Configuração SMTP ausente: PROPOSAL_NOTIFICATION_EMAIL"
        )
    return recipient_email


def _send_proposal_email(
    data: ProposalCreatedModel,
    recipient_email: str,
    subject: str,
    content: str,
) -> None:
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_password = os.getenv("SMTP_PASSWORD")
    sender_email = os.getenv("SMTP_FROM", smtp_user)

    required_settings = {
        "SMTP_HOST": smtp_host,
        "SMTP_USER": smtp_user,
        "SMTP_PASSWORD": smtp_password,
        "SMTP_FROM": sender_email,
    }

    missing_settings = [
        key for key, value in required_settings.items() if not value
    ]

    if missing_settings:
        raise RuntimeError(
            f"Configurações SMTP ausentes: {', '.join(missing_settings)}"
        )

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender_email
    message["To"] = recipient_email
    message.set_content(content)

    with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as smtp:
        smtp.starttls()
        smtp.login(smtp_user, smtp_password)
        smtp.send_message(message)


def send_customer_proposal_email(
    data: ProposalCreatedModel,
    recipient_email: str,
) -> None:
    proposal = data.data.proposal
    user = data.data.user
    car = data.data.car

    _send_proposal_email(
        data,
        recipient_email,
        "Recebemos sua proposta | Prime Motors",
        f"""
Olá, {user.name},

Recebemos sua proposta para o veículo {car.name}. Agradecemos pelo seu
interesse na Prime Motors.

RESUMO DA PROPOSTA
Veículo: {car.name}
Identificação: {proposal.id}
Valor ofertado: {_format_brl(proposal.offeredValue)}
Data de envio: {_format_proposal_date(proposal.createdAt)}

Sua mensagem:
{proposal.message or "Nenhuma mensagem foi incluída."}

Nossa equipe analisará sua proposta. Caso seja necessário, entraremos em
contato por este endereço de e-mail.

Atenciosamente,
Equipe Prime Motors
""".strip(),
    )


def send_internal_proposal_notification(
    data: ProposalCreatedModel,
    recipient_email: str,
) -> None:
    proposal = data.data.proposal
    user = data.data.user
    car = data.data.car

    _send_proposal_email(
        data,
        recipient_email,
        "Nova proposta recebida | Prime Motors",
        f"""
Olá, equipe Prime Motors,

Uma nova proposta foi recebida e está disponível para análise.

DADOS DA PROPOSTA
Identificação: {proposal.id}
Data de envio: {_format_proposal_date(proposal.createdAt)}
Veículo: {car.name}
Valor ofertado: {_format_brl(proposal.offeredValue)}
Status: {proposal.status}

DADOS DO CLIENTE
Nome: {user.name}
E-mail: {user.email}

Mensagem do cliente:
{proposal.message or "Nenhuma mensagem foi incluída."}

Atenciosamente,
Notificações Prime Motors
""".strip(),
    )
