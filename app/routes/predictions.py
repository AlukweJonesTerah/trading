# trading_platform_backend/app/routes/predictions.py

# API route for prediction logic

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.services.prediction_service import (
    forecast_prices_arima_sqlalchemy,
    forecast_prices_arima_mongo,
    predict_price_lstm_sqlalchemy,
    predict_price_lstm_mongo
)
from app.models import TradingPair, MongoTradingPair

router = APIRouter()


# ARIMA predictions using SQLAlchemy data
@router.get("/predict/sqlalchemy/arima/{symbol}", response_model=dict)
def predict_price_sqlalchemy_arima(symbol: str, db: Session = Depends(get_db)):
    """
    Predict the next price for a given trading pair using ARIMA and SQLAlchemy data.
    """
    # Fetch historical prices from SQLAlchemy
    trading_pairs = db.query(TradingPair).filter(TradingPair.symbol == symbol).all()

    if not trading_pairs:
        raise HTTPException(status_code=404, detail="Trading pair not found")

    # Extract historical prices
    historical_prices = [pair.price for pair in trading_pairs]

    try:
        # Use the ARIMA model to predict the next price
        predicted_price = forecast_prices_arima_sqlalchemy(historical_prices)
        return {"symbol": symbol, "predicted_price": predicted_price}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ARIMA predictions using MongoDB data
@router.get("/predict/mongo/arima/{symbol}", response_model=dict)
async def predict_price_mongo_arima(symbol: str):
    """
    Predict the next price for a given trading pair using ARIMA and MongoDB data.
    """
    # Fetch historical prices from MongoDB
    trading_pairs = await MongoTradingPair.find(MongoTradingPair.symbol == symbol).to_list(length=100)

    if not trading_pairs:
        raise HTTPException(status_code=404, detail="Trading pair not found")

    # Extract historical prices
    historical_prices = [pair.price for pair in trading_pairs]

    try:
        # Use the ARIMA model to predict the next price
        predicted_price = await forecast_prices_arima_mongo(symbol)
        return {"symbol": symbol, "predicted_price": predicted_price}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# LSTM predictions using SQLAlchemy data
@router.get("/predict/sqlalchemy/lstm/{symbol}", response_model=dict)
async def predict_price_sqlalchemy_lstm(symbol: str):
    """
    Predict the next price for a given trading pair using LSTM and SQLAlchemy data.
    """
    try:
        predicted_price = await predict_price_lstm_sqlalchemy(symbol)
        return {"symbol": symbol, "predicted_price": predicted_price}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# LSTM predictions using MongoDB data
@router.get("/predict/mongo/lstm/{symbol}", response_model=dict)
async def predict_price_mongo_lstm(symbol: str):
    """
    Predict the next price for a given trading pair using LSTM and MongoDB data.
    """
    try:
        predicted_price = await predict_price_lstm_mongo(symbol)
        return {"symbol": symbol, "predicted_price": predicted_price}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
