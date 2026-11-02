import os
import smtplib
from email.message import EmailMessage

from src.models.emailModel import ProposalCreatedModel


def send_proposal_created_email(data: ProposalCreatedModel) -> None:
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_password = os.getenv("SMTP_PASSWORD")
    sender_email = os.getenv("SMTP_FROM", smtp_user)
    recipient_email = os.getenv("PROPOSAL_NOTIFICATION_EMAIL")

    required_settings = {
        "SMTP_HOST": smtp_host,
        "SMTP_USER": smtp_user,
        "SMTP_PASSWORD": smtp_password,
        "SMTP_FROM": sender_email,
        "PROPOSAL_NOTIFICATION_EMAIL": recipient_email,
    }

    missing_settings = [
        key for key, value in required_settings.items() if not value
    ]

    if missing_settings:
        raise RuntimeError(
            f"Configurações SMTP ausentes: {', '.join(missing_settings)}"
        )

    message = EmailMessage()
    message["Subject"] = (
        f"Nova proposta recebida - {data.vehicle.brand} "
        f"{data.vehicle.model}"
    )
    message["From"] = sender_email
    message["To"] = recipient_email

    message.set_content(
        f"""
Uma nova proposta foi criada no Prime Motors.

ID da proposta: {data.proposal_id}

Cliente: {data.user.name}
E-mail do cliente: {data.user.email}

Veículo: {data.vehicle.brand} {data.vehicle.model}
Ano: {data.vehicle.year}
""".strip()
    )

    with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as smtp:
        smtp.starttls()
        smtp.login(smtp_user, smtp_password)
        smtp.send_message(message)
