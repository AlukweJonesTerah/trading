#trading_platform_backend/app/schemas.py

# Pydantic schemas for request/response validation

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


# Shared Pydantic Schemas for Validation and Serialization

class TradingPairCreate(BaseModel):
    symbol: str = Field(..., description="The trading pair symbol, e.g., 'BTC/USD'.")
    price: float = Field(..., description="The current price of the trading pair.")


class TradingPairResponse(TradingPairCreate):
    id: Optional[str]  # MongoDB will use a string for the ID, while SQLAlchemy uses an integer.

    class Config:
        orm_mode = True


class OrderCreate(BaseModel):
    symbol: str
    amount: float
    prediction: str
    trade_time: int


class OrderResponse(BaseModel):
    id: Optional[str]  # MongoDB will use a string for the ID, while SQLAlchemy uses an integer.
    user_id: Optional[str] #we user_id to match the return data
    symbol: str
    amount: float
    prediction: str
    trade_time: int
    start_time: datetime
    locked_price: float
    status: str

    class Config:
        orm_mode = True

