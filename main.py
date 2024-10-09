# trading_platform_backend/main.py

# Entry point for the FastAPI app

import asyncio
import logging
import os

from beanie import init_beanie
from decouple import config
from fastapi import FastAPI
from motor.motor_asyncio import AsyncIOMotorClient
from websockets.exceptions import ConnectionClosed, ConnectionClosedError
from slowapi.middleware import SlowAPIMiddleware
from slowapi import Limiter
from slowapi.util import get_remote_address
from app.models import MongoUser, MongoTradingPair, MongoOrder  # MongoDB models
from app.routes import trading, predictions, currencies
from app.utils import fetch_real_time_prices  # Removed get_redis_connection import
import dotenv

# FastAPI app initialization
app = FastAPI()
dotenv.load_dotenv(".env")
BASE_URL = os.getenv("BASE_URL")

# Rate limiting configuration
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load MongoDB URI and Database name from environment variables
MONGO_URI = config("MONGO_URI", default="mongodb://localhost:27017")
MONGO_DB_NAME = config("MONGO_DB_NAME", default="trading_db")

# Initialize MongoDB client and Beanie ODM
client = AsyncIOMotorClient(MONGO_URI)
db = client[MONGO_DB_NAME]

@app.on_event("startup")
async def startup_event():
    # Initialize MongoDB (NoSQL) with Beanie
    await init_beanie(database=db, document_models=[MongoUser, MongoTradingPair, MongoOrder])

    # Start the background task for fetching real-time prices
    asyncio.create_task(start_price_fetching_task())

@app.on_event("shutdown")
async def shutdown_event():
    print("Shutting down: canceling outstanding tasks")
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    [task.cancel() for task in tasks]
    await asyncio.gather(*tasks, return_exceptions=True)
    print("Shutdown complete.")


# Function to handle continuous price fetching and reconnections
async def start_price_fetching_task():
    while True:
        try:
            # Fetch real-time prices
            await fetch_real_time_prices()
        except (ConnectionClosed, ConnectionClosedError) as e:
            logger.error(f"WebSocket connection error: {e}. Reconnecting in 5 seconds...")
            print(f"WebSocket connection error: {e}. Reconnecting in 5 seconds...")
            await asyncio.sleep(5)  # Wait before attempting reconnection
        except Exception as e:
            logger.error(f"Unexpected error: {e}. Reconnecting in 5 seconds...")
            print(f"Unexpected error: {e}. Reconnecting in 5 seconds...")
            await asyncio.sleep(5)  # Wait before attempting reconnection


# Include routers for different endpoints
app.include_router(trading.router, prefix=f"/api/trading", tags=["Trading"])
app.include_router(predictions.router, prefix=f"/api/predictions", tags=["Predictions"])
# app.include_router(currencies.router, prefix=f"/api/currencies", tags=["Currencies"])
