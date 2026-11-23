
import hmac
import os

from fastapi import APIRouter, Header, HTTPException, Response, status

from src.controllers.emailController import handle_proposal_created
from src.models.emailModel import ProposalCreatedModel

router = APIRouter(prefix="/emails", tags=["Emails"])


@router.post("/proposal-created", status_code=status.HTTP_200_OK)
def proposal_created(
    data: ProposalCreatedModel,
    response: Response,
    x_service_token: str | None = Header(default=None),
):
    expected_token = os.getenv("SERVICE_TOKEN")

    if (
        not expected_token
        or not x_service_token
        or not hmac.compare_digest(
            x_service_token.encode("utf-8"),
            expected_token.encode("utf-8"),
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de serviço inválido.",
        )

    return handle_proposal_created(data, response)
