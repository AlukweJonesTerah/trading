# trading_platform_backend/main.py

# Entry point for the FastAPI app

import asyncio
import logging

from beanie import init_beanie
from decouple import config
from fastapi import FastAPI
from motor.motor_asyncio import AsyncIOMotorClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from websockets.exceptions import ConnectionClosed, ConnectionClosedError

from app.database import Base
from app.models import MongoUser, MongoTradingPair, MongoOrder  # MongoDB models
from app.routes import trading, predictions, currencies
from app.utils import fetch_real_time_prices

# FastAPI app initialization
app = FastAPI()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load MongoDB URI and Database name from environment variables
MONGO_URI = config("MONGO_URI", default="mongodb://localhost:27017")
MONGO_DB_NAME = config("MONGO_DB_NAME", default="trading_db")

# Async database engine and session creation for SQLAlchemy
SQLALCHEMY_DATABASE_URL = config("DATABASE_URL", default="sqlite+aiosqlite:///./test.db")
async_engine = create_async_engine(SQLALCHEMY_DATABASE_URL, echo=False, future=True)
AsyncSessionLocal = sessionmaker(bind=async_engine, class_=AsyncSession, expire_on_commit=False)


@app.on_event("startup")
async def startup_event():
    # Initialize SQLAlchemy (relational database) and create tables
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Initialize MongoDB (NoSQL) with Beanie
    client = AsyncIOMotorClient(MONGO_URI)
    db = client[MONGO_DB_NAME]
    await init_beanie(database=db, document_models=[MongoUser, MongoTradingPair, MongoOrder])

    # Start the background task for fetching real-time prices
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
            async with AsyncSessionLocal() as session:
                await fetch_real_time_prices(session)
        except (ConnectionClosed, ConnectionClosedError) as e:
            logger.error(f"WebSocket connection error: {e}. Reconnecting in 5 seconds...")
            await asyncio.sleep(5)  # Wait before attempting reconnection
        except Exception as e:
            logger.error(f"Unexpected error: {e}. Reconnecting in 5 seconds...")
            await asyncio.sleep(5)  # Wait before attempting reconnection


# Include routers for different endpoints
app.include_router(trading.router, prefix=f"{BASE_URL}/api/trading", tags=["Trading"])
app.include_router(predictions.router, prefix=f"{BASE_URL}/api/predictions", tags=["Predictions"])
app.include_router(currencies.router, prefix=f"{BASE_URL}/api/currencies", tags=["Currencies"])
