
from datetime import datetime
from decimal import Decimal
from html import escape
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


def _format_offer_comparison(asking_price: Decimal, offered_value: Decimal) -> str:
    difference = abs(asking_price - offered_value)
    if difference == 0:
        return "Valor ofertado igual ao valor anunciado."

    direction = "abaixo" if offered_value < asking_price else "acima"
    percentage = difference / asking_price * 100 if asking_price else Decimal(0)
    formatted_percentage = f"{percentage:.2f}".replace(".", ",")
    return (
        f"{_format_brl(difference)} {direction} do valor anunciado "
        f"({formatted_percentage}%)"
    )


def _render_html_email(
    greeting: str,
    introduction: str,
    sections: list[tuple[str, list[tuple[str, str]]]],
    closing: str,
) -> str:
    rendered_sections = []
    for heading, rows in sections:
        rendered_rows = "".join(
            (
                "<tr>"
                '<th style="padding:8px 12px;text-align:left;vertical-align:top;'
                'color:#526071;font-weight:600;">'
                f"{escape(label)}</th>"
                '<td style="padding:8px 12px;color:#182230;">'
                f"{escape(value)}</td>"
                "</tr>"
            )
            if label
            else (
                '<tr><td colspan="2" style="padding:8px 12px;color:#182230;'
                'white-space:pre-wrap;">'
                f"{escape(value)}</td></tr>"
            )
            for label, value in rows
        )
        rendered_sections.append(
            '<section style="margin:24px 0;">'
            '<h2 style="margin:0 0 8px;color:#17365d;font-size:16px;">'
            f"{escape(heading)}</h2>"
            '<table role="presentation" style="width:100%;border-collapse:collapse;'
            "background:#f5f7fa;border-radius:8px;\">"
            f"{rendered_rows}</table></section>"
        )

    return (
        '<!doctype html><html lang="pt-BR"><body style="margin:0;padding:24px;'
        'background:#f2f4f7;font-family:Arial,Helvetica,sans-serif;color:#182230;">'
        '<main style="max-width:640px;margin:0 auto;padding:32px;background:#ffffff;'
        'border:1px solid #e4e7ec;border-radius:12px;">'
        '<p style="font-size:16px;">'
        f"{escape(greeting)}</p>"
        f'<p style="line-height:1.6;">{escape(introduction)}</p>'
        f'{"".join(rendered_sections)}'
        '<p style="margin-top:28px;line-height:1.6;">'
        f"{escape(closing).replace(chr(10), '<br>')}</p>"
        "</main></body></html>"
    )


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
    html_content: str,
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
    message.add_alternative(html_content, subtype="html")

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
    proposal_message = proposal.message or "Nenhuma mensagem foi incluída."
    comparison = _format_offer_comparison(car.value, proposal.offeredValue)
    content = f"""
Prezado(a) {user.name},

Recebemos sua proposta para o veículo {car.name}. Agradecemos pelo seu interesse
na Prime Motors.

RESUMO DA PROPOSTA
Veículo: {car.name}
Protocolo: {proposal.id}
Valor anunciado: {_format_brl(car.value)}
Valor ofertado: {_format_brl(proposal.offeredValue)}
{comparison}
Data de envio: {_format_proposal_date(proposal.createdAt)}

PRÓXIMOS PASSOS
Nossa equipe analisará sua proposta e entrará em contato por este endereço de
e-mail assim que houver uma atualização.

Sua mensagem:
{proposal_message}

Atenciosamente,
Equipe Prime Motors
""".strip()
    html_content = _render_html_email(
        f"Prezado(a) {user.name}",
        (
            f"Recebemos sua proposta para {car.name}. "
            "Agradecemos pelo seu interesse na Prime Motors."
        ),
        [
            (
                "RESUMO DA PROPOSTA",
                [
                    ("Veículo", car.name),
                    ("Protocolo", proposal.id),
                    ("Valor anunciado", _format_brl(car.value)),
                    ("Valor ofertado", _format_brl(proposal.offeredValue)),
                    ("Comparativo", comparison),
                    ("Data de envio", _format_proposal_date(proposal.createdAt)),
                ],
            ),
            (
                "PRÓXIMOS PASSOS",
                [
                    (
                        "",
                        "Nossa equipe analisará sua proposta e entrará em "
                        "contato por este endereço de e-mail assim que "
                        "houver uma atualização.",
                    )
                ],
            ),
            ("SUA MENSAGEM", [("", proposal_message)]),
        ],
        "Atenciosamente,\nEquipe Prime Motors",
    )

    _send_proposal_email(
        data,
        recipient_email,
        "Recebemos sua proposta | Prime Motors",
        content,
        html_content,
    )


def send_internal_proposal_notification(
    data: ProposalCreatedModel,
    recipient_email: str,
) -> None:
    proposal = data.data.proposal
    user = data.data.user
    car = data.data.car
    proposal_message = proposal.message or "Nenhuma mensagem foi incluída."
    content = f"""
Olá, equipe Prime Motors,

Uma nova proposta foi recebida e requer análise da equipe.

DADOS DA PROPOSTA
Protocolo: {proposal.id}
Data de envio: {_format_proposal_date(proposal.createdAt)}
Veículo: {car.name}
Valor anunciado: {_format_brl(car.value)}
Valor ofertado: {_format_brl(proposal.offeredValue)}
Status: {proposal.status}

DADOS DO CLIENTE
Nome: {user.name}
E-mail: {user.email}

MENSAGEM DO CLIENTE
{proposal_message}

AÇÃO NECESSÁRIA
Analise os dados da proposta e entre em contato com o cliente quando houver
uma definição.

Atenciosamente,
Notificações Prime Motors
""".strip()
    html_content = _render_html_email(
        "Olá, equipe Prime Motors",
        "Uma nova proposta foi recebida e requer análise da equipe.",
        [
            (
                "DADOS DA PROPOSTA",
                [
                    ("Protocolo", proposal.id),
                    ("Data de envio", _format_proposal_date(proposal.createdAt)),
                    ("Veículo", car.name),
                    ("Valor anunciado", _format_brl(car.value)),
                    ("Valor ofertado", _format_brl(proposal.offeredValue)),
                    ("Status", proposal.status),
                ],
            ),
            (
                "DADOS DO CLIENTE",
                [("Nome", user.name), ("E-mail", str(user.email))],
            ),
            ("MENSAGEM DO CLIENTE", [("", proposal_message)]),
            (
                "AÇÃO NECESSÁRIA",
                [
                    (
                        "",
                        "Analise os dados da proposta e entre em contato "
                        "com o cliente quando houver uma definição.",
                    )
                ],
            ),
        ],
        "Atenciosamente,\nNotificações Prime Motors",
    )

    _send_proposal_email(
        data,
        recipient_email,
        "Nova proposta recebida | Prime Motors",
        content,
        html_content,
    )
