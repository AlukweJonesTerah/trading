# trading_platform_backend/app/database.py

# Database connection and session management

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import motor.motor_asyncio
from decouple import config

# SQLAlchemy (Relational DB) Configuration
DATABASE_URL = config("DATABASE_URL", default="sqlite:///./trading.db")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# MongoDB (NoSQL) Configuration
MONGO_URI = config("MONGO_URI", default="mongodb://localhost:27017")
MONGO_DB_NAME = config("MONGO_DB_NAME", default="trading_platform")

client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI)
database = client[MONGO_DB_NAME]

# Dependency to get the SQLAlchemy DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
