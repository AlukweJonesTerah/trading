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
    # This will fetch prices every 60 seconds in the background.
    asyncio.create_task(fetch_real_time_prices(SessionLocal()))


@app.on_event("shutdown")
async def shutdown_event():
    # Any cleanup tasks can be handled here
    pass


# Include routers for different endpoints
app.include_router(trading.router, prefix="/api/trading", tags=["Trading"])
app.include_router(predictions.router, prefix="/api/predictions", tags=["Predictions"])
app.include_router(currencies.router, prefix="/api/currencies", tags=["Currencies"])


