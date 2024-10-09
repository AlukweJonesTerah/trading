# Script to create a dummy user

# trading_platform_backend/scripts/create_dummy_user.py

from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient
from app.models import MongoUser
from decouple import config

async def create_dummy_user():
    # Database setup
    MONGO_URI = config("MONGO_URI", default="mongodb://localhost:27017")
    MONGO_DB_NAME = config("MONGO_DB_NAME", default="trading_db")

    client = AsyncIOMotorClient(MONGO_URI)
    db = client[MONGO_DB_NAME]
    await init_beanie(database=db, document_models=[MongoUser])

    existing_user = await MongoUser.find_one(MongoUser.email == "testuser@example.com")
    if existing_user:
        return {"message": "Dummy user already exists", "user_id": str(existing_user.id)}

    # Dummy user details
    dummy_user = MongoUser(
        username="testuser",
        email="testuser@example.com",
        hashed_password="hashedpassword",  # Use a proper hashing mechanism in real scenarios
        balance=1000.0,
        is_active=True
    )

    # Insert dummy user into the database
    await dummy_user.insert()
    return {"message": "Dummy user created successfully", "user_id": str(dummy_user.id)}

# Run the function using asyncio
import asyncio
asyncio.run(create_dummy_user())
