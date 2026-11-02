from fastapi import HTTPException, status

from src.models.emailModel import ProposalCreatedModel
from src.services.emailService import send_proposal_created_email


def handle_proposal_created(data: ProposalCreatedModel) -> dict:
    if data.event != "proposal.created":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Evento não suportado.",
        )

    try:
        send_proposal_created_email(data)
    except RuntimeError as error:
        # Configuração do serviço ausente ou inválida.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="O serviço de e-mail não está configurado corretamente.",
        ) from error
    except Exception as error:
        # Falha de conexão ou envio SMTP.
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Não foi possível enviar o e-mail da proposta.",
        ) from error

    return {
        "message": "E-mail da proposta enviado com sucesso.",
        "proposal_id": data.proposal_id,
    }
