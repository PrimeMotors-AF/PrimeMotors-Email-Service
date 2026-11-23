from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, EmailStr


class ProposalModel(BaseModel):
    id: str
    offeredValue: Decimal
    message: str | None
    status: str
    createdAt: datetime


class UserModel(BaseModel):
    id: str
    name: str
    email: EmailStr


class CarModel(BaseModel):
    id: str
    name: str
    value: Decimal


class ProposalCreatedDataModel(BaseModel):
    proposal: ProposalModel
    user: UserModel
    car: CarModel


class ProposalCreatedModel(BaseModel):
    event: str
    data: ProposalCreatedDataModel
