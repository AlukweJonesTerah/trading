# trading_platform_backend/app/routes/trading.py

# Routes for handling trading logic

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session
from beanie import PydanticObjectId
from cachetools import TTLCache
from fastapi.security import OAuth2PasswordRequestForm
import asyncio

from app.database import get_db, SessionLocal
from app.schemas import TradingPairResponse, OrderCreate, OrderResponse
from app.services import trading_service
from app.models import MongoTradingPair, MongoUser, MongoOrder
from app.utils import fetch_real_time_prices, cache_lock
from fastapi.security import OAuth2PasswordBearer
from app.services.trading_service import validate_trade
from jose import jwt, JWTError
import logging
import app.services.trading_service
from app.dependencies import get_current_user_id

router = APIRouter()

logger = logging.getLogger(__name__)

@router.websocket("/ws/prices")
async def websocket_prices(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            prices = await fetch_real_time_prices()
            await websocket.send_json(prices)
            await asyncio.sleep(1)  # Send updates every second
    except WebSocketDisconnect:
        pass


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from jose import jwt
from pydantic import ValidationError

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def decode_token(token: str):
    SECRET_KEY = "helpme1234"  # Use your actual secret key configured for JWT
    ALGORITHM = "HS256"
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.JWTError:
        raise HTTPException(status_code=401, detail="Could not validate credentials")

async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(status_code=401, detail="Could not validate credentials")
    try:
        payload = decode_token(token)
        user_id = payload.get("user_id")
        if not user_id:
            logger.error("User ID not found in token")
            raise HTTPException(status_code=401, detail="Could not validate credentials")
        user = await MongoUser.get(PydanticObjectId(user_id))
        if not user:
            logger.error(f"User not found: {user_id}")
            raise HTTPException(status_code=404, detail="User not found")
        return user
    except jwt.JWTError as e:
        logger.error(f"JWT Error: {str(e)}")
        raise HTTPException(status_code=401, detail="Could not validate credentials")
    except ValidationError as e:
        logger.error(f"Validation Error: {str(e)}")
        raise credentials_exception


# Dummy function to simulate getting a user without authentication
async def get_dummy_user():
    try:
        # Attempt to fetch an existing dummy user or create a new one
        dummy_user = await MongoUser.find_one(MongoUser.username == "dummy_user")
        if not dummy_user:
            # Create a new dummy user if not found
            dummy_user = MongoUser(
                username="dummy_user",
                email="dummy@example.com",
                hashed_password="hashed_test_pwd",  # Normally you would hash this password
                balance=1000.0,
                is_active=True
            )
            await dummy_user.insert()
        return dummy_user
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create or retrieve dummy user: {str(e)}")


@router.post("/api/trades/place_order", response_model=OrderResponse)
async def place_order(order: OrderCreate):  #  , user_id: str = Depends(get_current_user_id)
    """
    Endpoint to place an order with the current real-time price for the trading pair.
    """
    try:
        # Place the order with real-time price and return the response
        order_response = await trading_service.place_order_with_real_time_price(order)  # , user_id
        return order_response
    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"Error placing order: {e}")
        raise HTTPException(status_code=500, detail="An unexpected error occurred while placing the order.")

# @router.post("/api/trades/place_order", response_model=OrderResponse, tags=["Trading"])
# async def place_order(order: OrderCreate):
#     """
#     Place an order based on real-time pricing data without authentication for testing purposes.
#     """
#     logger.info("Received order placement request.")
#
#     # Create a dummy user for testing purposes
#     try:
#         user = get_dummy_user()
#     except Exception as e:
#         logger.error(f"Failed to create or retrieve dummy user: {e}")
#         raise HTTPException(status_code=500, detail="Failed to create or retrieve dummy user")
#
#     # Validate trade data
#     try:
#         validate_trade(order)
#     except HTTPException as e:
#         logger.error(f"Trade validation failed: {e.detail}")
#         raise e
#
#     # Fetch real-time prices
#     try:
#         prices = await fetch_real_time_prices()
#         if not prices.get(order.symbol):
#             logger.error("Real-time price not available for the trading pair.")
#             raise HTTPException(status_code=404, detail="Real-time price not available for the trading pair.")
#     except Exception as e:
#         logger.error(f"Failed to fetch real-time prices: {e}")
#         raise HTTPException(status_code=500, detail="Failed to fetch real-time prices")
#
#     current_price = prices[order.symbol]
#
#     # Check user balance
#     if user.balance < order.amount:
#         logger.error("Insufficient balance.")
#         raise HTTPException(status_code=400, detail="Insufficient balance")
#
#     # Place the order with the fetched real-time price
#     try:
#         mongo_order = trading_service.place_order_with_real_time_price(order, str(user.id), current_price)
#     except Exception as e:
#         logger.error(f"Failed to place order: {e}")
#         raise HTTPException(status_code=500, detail="Failed to place order")
#
#     logger.info("Order placed successfully.")
#     return mongo_order

@router.get("/trades/real_time", response_model=dict)
async def get_real_time_prices_endpoint():
    """
    Endpoint to fetch real-time prices for cryptocurrencies and fiat currencies directly from external APIs
    without saving them to the database.
    """
    prices = await fetch_real_time_prices()
    if not prices:
        raise HTTPException(status_code=500, detail="Failed to fetch real-time prices.")
    return prices


@router.post("/trades/real_time", response_model=OrderResponse)
async def place_order_with_real_time(order: OrderCreate):
    user_id = "66ffdd01e83feefe5311806e"  # Example hardcoded user ID
    try:
        order_response = await place_order(order)
        return order_response
    except HTTPException as e:
        raise e


@router.get("/trading_pairs/mongo")
async def get_mongo_trading_pairs():
    trading_pairs = await MongoTradingPair.find_all().to_list()
    return [{"symbol": pair.symbol, "price": pair.price} for pair in trading_pairs]


@router.get("/balance", response_model=dict)
async def get_user_balance():
    # Replace with the appropriate user session or user fetching logic
    user = await MongoUser.get(PydanticObjectId("651b9fb89f4c6e8f1b2f1f9c"))  # Hardcoded for now
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return {"balance": user.balance}

@router.get("/{order_id}", response_model=OrderResponse)
async def get_order(order_id: str):
    """
    Retrive an order by its ID
    :param order_id:
    :return: order
    """
    order = await MongoOrder.get(PydanticObjectId(order_id))
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order

@router.post("/create_dummy_user", response_model=dict)
async def create_dummy_user():
    dummy_user = MongoUser(
        username="dummy_user",
        email="dummy@example.com",
        hashed_password="hashed_test_pwd",
        balance=1000.0,  # Adjust balance as needed
        is_active=True
    )
    await dummy_user.insert()
    return {"message": "Dummy user created successfully", "user_id": str(dummy_user.id)}
