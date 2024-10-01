# trading_platform_backend/app/routes/trading.py

# Routes for handling trading logic

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session
from beanie import PydanticObjectId

from app.database import get_db, SessionLocal
from app.schemas import TradingPairResponse, OrderCreate, OrderResponse
from app.services import trading_service
import asyncio
from app.models import TradingPair, MongoTradingPair, MongoUser
from app.utils import fetch_real_time_prices

router = APIRouter()


@router.websocket("/ws/prices")
async def websocket_prices(websocket: WebSocket, db: Session = Depends(get_db)):
    await websocket.accept()
    try:
        while True:
            # Fetch the latest prices from the relational database (SQLAlchemy)
            prices_sqlalchemy = db.query(TradingPair).all()
            price_data_sqlalchemy = [{"symbol": pair.symbol, "price": pair.price} for pair in prices_sqlalchemy]

            # Fetch the latest prices from the NoSQL database (MongoDB)
            prices_mongodb = await MongoTradingPair.find_all().to_list()
            price_data_mongodb = [{"symbol": pair.symbol, "price": pair.price} for pair in prices_mongodb]

            # Combine the results from both databases
            combined_price_data = price_data_sqlalchemy + price_data_mongodb

            # Send the combined price data to the client
            await websocket.send_json(combined_price_data)
            await asyncio.sleep(1)  # Send updates every second
    except WebSocketDisconnect:
        pass


@router.post("/trades/", response_model=OrderResponse)
async def place_order(order: OrderCreate, db: Session = Depends(get_db)):
    # Validate trade data
    trading_service.validate_trade(order)

    # Placeholder logic for user_id, should be replaced by actual user session logic
    user_id = "some_mongo_user_id"

    # Decide which database to use for the order
    if order.symbol in ["BTC/USD", "ETH/USD"]:  # Example condition to use MongoDB
        db_order = await trading_service.place_order_mongo(order, user_id)
    else:
        db_order = trading_service.place_order_sqlalchemy(db, order, 1)

    return db_order


@router.get("/trades/real_time", response_model=dict)
async def get_real_time_prices():
    """
    Fetch real-time prices for cryptocurrencies and fiat currencies directly from external APIs
    without saving them to the database.
    """
    prices = await fetch_real_time_prices(SessionLocal())
    if not prices:
        raise HTTPException(status_code=500, detail="Failed to fetch real-time prices.")

    return prices

@router.post("/trades/real_time", response_model=OrderResponse)
async def place_order_with_real_time(order: OrderCreate):
    user_id = "651b9fb89f4c6e8f1b2f1f9c"
    try:
        db_order = await trading_service.place_order_with_real_time_price(order, user_id) # user_id
        return db_order
    except HTTPException as e:
        raise e

@router.get("/trading_pairs/sqlalchemy")
def get_sqlalchemy_trading_pairs(db: Session = Depends(get_db)):
    trading_pairs = db.query(TradingPair).all()
    return [{"symbol": pair.symbol, "price": pair.price} for pair in trading_pairs]

@router.get("/trading_pairs/mongo")
async def get_mongo_trading_pairs():
    trading_pairs = await MongoTradingPair.find_all().to_list()
    return [{"symbol": pair.symbol, "price": pair.price} for pair in trading_pairs]

@router.get("/balance", response_model=dict)
async def get_user_balance():
    # Replace with the appropriate user session or user fetching logic
    user = await MongoUser.get(PydanticObjectId("some_mongo_user_id"))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return {"balance": user.balance}
