from pydantic import BaseModel, EmailStr


class UserModel(BaseModel):
    name: str
    email: EmailStr


class VehicleModel(BaseModel):
    brand: str
    model: str
    year: int


class ProposalCreatedModel(BaseModel):
    event: str
    proposal_id: str
    user: UserModel
    vehicle: VehicleModel
