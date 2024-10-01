# trading_platform_backend/app/models.py

# SQLAlchemy models for the app

from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base
from typing import Optional
from datetime import datetime
from beanie import Document, Indexed, PydanticObjectId
from pydantic import Field


# SQLAlchemy Models (Relational Database)

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, nullable=False)
    email = Column(String, unique=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    balance = Column(Float, default=0.0)
    is_active = Column(Boolean, default=True)


class TradingPair(Base):
    __tablename__ = "trading_pairs"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, unique=True, nullable=False)
    price = Column(Float, nullable=True)


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    symbol = Column(String, nullable=False)  # Currency pair symbol
    amount = Column(Float, nullable=False)  # Bet amount
    prediction = Column(String, nullable=False)  # 'rise' or 'fall'
    trade_time = Column(Integer, nullable=False)  # Trade duration in seconds
    start_time = Column(DateTime, nullable=False)  # Time when the order was placed
    locked_price = Column(Float, nullable=False)  # Price at the time the order was placed
    status = Column(String, default="pending")  # Status: 'pending', 'win', 'lose'
    payout = Column(Float, nullable=True)  # Payout for the order (if won)
    user = relationship("User")


# MongoDB Models (NoSQL Database)

class MongoUser(Document):
    username: str
    email: str
    hashed_password: str
    balance: float = 0.0
    is_active: bool = True

    class Settings:
        collection = "users"


class MongoTradingPair(Document):
    # symbol: str = Indexed(str, unique=True)
    # price: float
    symbol: str = Field(...)
    price: float = Field(...)

    class Settings:
        collection = "trading_pairs"


class MongoOrder(Document):
    user_id: PydanticObjectId  # Add this field to store the user's ID    symbol: str
    symbol: str
    amount: float
    prediction: str  # 'rise' or 'fall'
    trade_time: int
    start_time: datetime = Field(default_factory=datetime.utcnow)
    locked_price: float
    status: str = 'pending'  # 'pending', 'win', 'lose'
    payout: Optional[float] = None

    class Settings:
        collection = "orders"
