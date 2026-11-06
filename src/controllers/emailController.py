
import logging

from fastapi import HTTPException, Response, status
from redis import Redis

from src.database.connection import SessionLocal
from src.models.emailModel import ProposalCreatedModel
from src.models.proposalModel import Proposal
from src.services.emailIdempotencyService import (
    EmailIdempotencyUnavailable,
    EmailProcessingInProgress,
    cache_email_sent,
    email_was_sent,
    lock_proposal_email_processing,
)
from src.services.emailRateLimitService import (
    EmailRateLimitExceeded,
    reserve_email_sends,
)
from src.services.emailService import (
    get_proposal_notification_email,
    send_customer_proposal_email,
    send_internal_proposal_notification,
)


logger = logging.getLogger(__name__)


def handle_proposal_created(
    data: ProposalCreatedModel,
    response: Response,
) -> dict:
    if data.event != "proposal.created":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Evento não suportado.",
        )

    try:
        with lock_proposal_email_processing(data.data.proposal.id) as redis:
            return _process_proposal_created(data, response, redis)
    except EmailProcessingInProgress as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="A proposta já está sendo processada.",
            headers={"Retry-After": "5"},
        ) from error
    except EmailIdempotencyUnavailable as error:
        logger.exception("Email idempotency protection is unavailable")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Não foi possível verificar a proteção contra envios duplicados.",
            headers={"Retry-After": "5"},
        ) from error


def _process_proposal_created(
    data: ProposalCreatedModel,
    response: Response,
    redis: Redis,
) -> dict:
    db = SessionLocal()

    try:
        proposal_data = data.data.proposal

        proposal = (
            db.query(Proposal)
            .filter(Proposal.proposal_id == proposal_data.id)
            .first()
        )

        if proposal is None:
            proposal = Proposal(
                proposal_id=proposal_data.id,
                user_name=data.data.user.name,
                user_email=str(data.data.user.email),
                car_name=data.data.car.name,
                offered_value=proposal_data.offeredValue,
                message=proposal_data.message,
                date_offer=proposal_data.createdAt,
                customer_email_sent=False,
                notification_email_sent=False,
            )
            db.add(proposal)
            db.commit()
            db.refresh(proposal)
        elif proposal.user_email.strip().lower() != str(
            data.data.user.email
        ).strip().lower():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="O evento não corresponde ao e-mail registrado para a proposta.",
            )

        cache_reconciled = False
        if not proposal.customer_email_sent and email_was_sent(
            redis,
            proposal_data.id,
            "customer",
        ):
            proposal.customer_email_sent = True
            cache_reconciled = True
        if not proposal.notification_email_sent and email_was_sent(
            redis,
            proposal_data.id,
            "internal",
        ):
            proposal.notification_email_sent = True
            cache_reconciled = True
        if cache_reconciled:
            db.commit()

        if proposal.customer_email_sent and proposal.notification_email_sent:
            return {
                "message": "Proposta já recebida anteriormente.",
                "proposal_id": proposal_data.id,
            }

        pending_customer_email = not proposal.customer_email_sent
        pending_internal_email = not proposal.notification_email_sent
        notification_email = (
            get_proposal_notification_email() if pending_internal_email else None
        )
        pending_email_count = int(pending_customer_email) + int(
            pending_internal_email
        )
        rate_limit = reserve_email_sends(
            db,
            proposal.user_email if pending_customer_email else None,
            pending_email_count,
        )
        response.headers["RateLimit-Limit"] = str(rate_limit.limit)
        response.headers["RateLimit-Remaining"] = str(rate_limit.remaining)
        response.headers["RateLimit-Reset"] = str(rate_limit.reset)
        response.headers["RateLimit-Policy"] = (
            f"{rate_limit.limit};w={rate_limit.window_seconds}"
        )

        if pending_customer_email:
            send_customer_proposal_email(data, proposal.user_email)
            cache_email_sent(redis, proposal_data.id, "customer")
            proposal.customer_email_sent = True
            db.commit()

        if pending_internal_email:
            if not notification_email:
                raise RuntimeError(
                    "Configuração SMTP ausente: PROPOSAL_NOTIFICATION_EMAIL"
                )
            send_internal_proposal_notification(data, notification_email)
            cache_email_sent(redis, proposal_data.id, "internal")
            proposal.notification_email_sent = True
            db.commit()

    except EmailIdempotencyUnavailable:
        db.rollback()
        raise

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

    except EmailRateLimitExceeded as error:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Limite de envio de e-mails excedido. Tente novamente mais tarde.",
            headers={
                "RateLimit-Limit": str(error.limit),
                "RateLimit-Remaining": "0",
                "RateLimit-Reset": str(error.retry_after),
                "RateLimit-Policy": f"{error.limit};w={error.window_seconds}",
                "Retry-After": str(error.retry_after),
            },
        ) from error

    except HTTPException:
        db.rollback()
        raise

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
        "message": "Proposta salva e e-mails enviados com sucesso.",
        "proposal_id": data.data.proposal.id,
    }
