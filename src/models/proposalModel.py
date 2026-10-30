import uuid

from sqlalchemy import Column, String, Numeric, Text, DateTime
from sqlalchemy.sql import func

from src.database.connection import Base


class Proposal(Base):
    __tablename__ = "proposals"

    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )

    proposal_id = Column(String(36), unique=True, nullable=False)

    user_name = Column(String(150), nullable=False)
    user_email = Column(String(255), nullable=False)

    car_name = Column(String(150), nullable=False)

    offered_value = Column(Numeric(10, 2), nullable=False)

    message = Column(Text, nullable=True)

    date_offer = Column(DateTime, nullable=False)

    created_at = Column(DateTime, server_default=func.now(), nullable=False)