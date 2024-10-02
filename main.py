# trading_platform_backend/main.py

# Entry point for the FastAPI app

import asyncio
from fastapi import FastAPI
from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie
from app.database import Base, engine, SessionLocal
from app.routes import trading, predictions, currencies
from app.utils import fetch_real_time_prices
from app.models import MongoUser, MongoTradingPair, MongoOrder  # MongoDB models
from decouple import config
from websockets.exceptions import ConnectionClosed, ConnectionClosedError

# FastAPI app initialization
app = FastAPI()

# Load MongoDB URI and Database name from environment variables
MONGO_URI = config("MONGO_URI", default="mongodb://localhost:27017")
MONGO_DB_NAME = config("MONGO_DB_NAME", default="trading_db")


@app.on_event("startup")
async def startup_event():
    # Initialize SQLAlchemy (relational database) and create tables
    Base.metadata.create_all(bind=engine)

    # Initialize MongoDB (NoSQL) with Beanie
    client = AsyncIOMotorClient(MONGO_URI)
    db = client[MONGO_DB_NAME]
    await init_beanie(database=db, document_models=[MongoUser, MongoTradingPair, MongoOrder])

    # Start the background task for fetching real-time prices
    # This will fetch prices continuously in the background, handling reconnections.
    asyncio.create_task(start_price_fetching_task())


@app.on_event("shutdown")
async def shutdown_event():
    # Any cleanup tasks can be handled here
    pass


# Function to handle continuous price fetching and reconnections
async def start_price_fetching_task():
    while True:
        try:
            # Fetch real-time prices, which internally handles WebSocket connections
            await fetch_real_time_prices(SessionLocal())
        except (ConnectionClosed, ConnectionClosedError) as e:
            print(f"WebSocket connection error: {e}. Reconnecting in 5 seconds...")
            await asyncio.sleep(5)  # Wait before attempting reconnection
        except Exception as e:
            print(f"Unexpected error: {e}. Reconnecting in 5 seconds...")
            await asyncio.sleep(5)  # Wait before attempting reconnection


# Include routers for different endpoints
app.include_router(trading.router, prefix="/api/trading", tags=["Trading"])
app.include_router(predictions.router, prefix="/api/predictions", tags=["Predictions"])
app.include_router(currencies.router, prefix="/api/currencies", tags=["Currencies"])
