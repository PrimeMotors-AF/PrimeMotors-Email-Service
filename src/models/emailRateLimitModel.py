from sqlalchemy import BigInteger, Column, Integer, String

from src.database.connection import Base


class EmailRateLimit(Base):
    __tablename__ = "email_rate_limits"

    key_hash = Column(String(64), primary_key=True)
    window_start = Column(BigInteger, nullable=False)
    attempts = Column(Integer, nullable=False, default=0)
