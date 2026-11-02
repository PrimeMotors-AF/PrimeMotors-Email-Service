
from fastapi import APIRouter, Header, HTTPException, status

from src.controllers.emailController import handle_proposal_created
from src.models.emailModel import ProposalCreatedModel

router = APIRouter(prefix="/emails", tags=["Emails"])


@router.post("/proposal-created", status_code=status.HTTP_200_OK)
def proposal_created(
    data: ProposalCreatedModel,
    x_service_token: str | None = Header(default=None),
):
    import os

    expected_token = os.getenv("SERVICE_TOKEN")

    if not expected_token or x_service_token != expected_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de serviço inválido.",
        )

    return handle_proposal_created(data)
