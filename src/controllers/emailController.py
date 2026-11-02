
import logging

from fastapi import HTTPException, status

from src.database.connection import SessionLocal
from src.models.emailModel import ProposalCreatedModel
from src.models.proposalModel import Proposal
from src.services.emailService import send_proposal_created_email


logger = logging.getLogger(__name__)


def handle_proposal_created(data: ProposalCreatedModel) -> dict:
    if data.event != "proposal.created":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Evento não suportado.",
        )

    db = SessionLocal()

    try:
        proposal_data = data.data.proposal

        existing_proposal = (
            db.query(Proposal)
            .filter(Proposal.proposal_id == proposal_data.id)
            .first()
        )

        if existing_proposal:
            return {
                "message": "Proposta já recebida anteriormente.",
                "proposal_id": proposal_data.id,
            }

        proposal = Proposal(
            proposal_id=proposal_data.id,
            user_name=data.data.user.name,
            user_email=data.data.user.email,
            car_name=data.data.car.name,
            offered_value=proposal_data.offeredValue,
            message=proposal_data.message,
            date_offer=proposal_data.createdAt,
        )

        db.add(proposal)
        db.commit()

        send_proposal_created_email(data)

    except RuntimeError as error:
        db.rollback()
        logger.exception(
            "Erro de configuração do serviço de e-mail: %s",
            error,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="O serviço de e-mail não está configurado corretamente.",
        ) from error

    except Exception as error:
        db.rollback()
        logger.exception(
            "Erro ao processar proposta %s",
            data.data.proposal.id,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Não foi possível processar a proposta.",
        ) from error

    finally:
        db.close()

    return {
        "message": "Proposta salva e e-mail enviado com sucesso.",
        "proposal_id": data.data.proposal.id,
    }
