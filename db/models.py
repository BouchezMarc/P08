from sqlalchemy import Column, BigInteger, Boolean, TIMESTAMP, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class Prediction(Base):
    __tablename__ = "predictions"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    created_at = Column(TIMESTAMP, server_default=func.now())
    input_features = Column(JSONB, nullable=False)
    prediction = Column(Boolean, nullable=False)