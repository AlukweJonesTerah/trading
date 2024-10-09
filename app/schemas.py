# trading_platform_backend/app/schemas.py

# Pydantic schemas for request/response validation

from pydantic import BaseModel, Field, EmailStr
from typing import Optional
from datetime import datetime

# Shared Pydantic Schemas for Validation and Serialization

# 1. User Schemas

class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, description="Username for the user")
    email: EmailStr = Field(..., description="The user's email address")
    password: str = Field(..., min_length=6, description="Password for the user")

class UserResponse(BaseModel):
    id: Optional[int]  # SQLAlchemy will return an integer ID, MongoDB will use a string
    username: str
    email: str
    balance: float
    is_active: bool

    class Config:
        orm_mode = True

# 2. Trading Pair Schemas
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
    prediction: str = Field(..., pattern="^(rise|fall)$", description="Prediction: 'rise' or 'fall'")
    trade_time: int  # Trade duration in seconds


class OrderResponse(BaseModel):
    id: Optional[str]  # MongoDB will use a string for the ID, while SQLAlchemy uses an integer.
    user_id: Optional[str]  # Add user_id to match the return data
    symbol: str
    amount: float
    prediction: str
    trade_time: int
    start_time: datetime
    locked_price: float
    status: str
    payout: Optional[float] = None

    class Config:
        orm_mode = True
