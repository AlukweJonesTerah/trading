# trading_platform_backend/app/services/prediction_service.py

# Business logic for price forecasting

import pandas as pd
from statsmodels.tsa.arima.model import ARIMA
from app.services.lstm_model import prepare_data, build_lstm_model, train_lstm_model, make_predictions
from app.database import SessionLocal
from app.models import TradingPair, MongoTradingPair
from sqlalchemy.orm import Session


# ARIMA Forecasting for SQLAlchemy (Relational Database)
def forecast_prices_arima_sqlalchemy(historical_prices):
    """
    Forecast the next price based on historical data using ARIMA.
    :param historical_prices: List of historical price data.
    :return: Predicted next price.
    """
    if len(historical_prices) < 10:  # Ensure there's enough data for ARIMA
        raise ValueError("Not enough data to perform prediction")

    # Convert to DataFrame for ARIMA model
    df = pd.DataFrame(historical_prices, columns=['price'])

    # Fit the ARIMA model
    model = ARIMA(df['price'], order=(5, 1, 0))
    model_fit = model.fit()

    # Forecast the next price (1 step ahead)
    forecast = model_fit.forecast(steps=1)[0]
    return forecast


async def forecast_prices_arima_mongo(symbol: str):
    """
    Forecast the next price based on historical data from MongoDB using ARIMA.
    :param symbol: The trading pair symbol.
    :return: Predicted next price.
    """
    # Fetch historical prices from MongoDB
    historical_data = await MongoTradingPair.find(MongoTradingPair.symbol == symbol).to_list(length=100)

    if len(historical_data) < 10:
        raise ValueError("Not enough data to perform prediction")

    historical_prices = [data.price for data in historical_data]

    # Convert to DataFrame for ARIMA model
    df = pd.DataFrame(historical_prices, columns=['price'])

    # Fit the ARIMA model
    model = ARIMA(df['price'], order=(5, 1, 0))
    model_fit = model.fit()

    # Forecast the next price (1 step ahead)
    forecast = model_fit.forecast(steps=1)[0]
    return forecast


async def predict_price_lstm_mongo(symbol: str):
    """
    Predict the next price for a given trading pair using an LSTM model from MongoDB data.
    :param symbol: The trading pair symbol (e.g., BTC/USD)
    :return: Predicted next price
    """
    # Fetch historical prices for the symbol from MongoDB
    trading_pairs = await MongoTradingPair.find(MongoTradingPair.symbol == symbol).to_list(length=100)

    if len(trading_pairs) < 10:  # Ensure sufficient data for LSTM
        raise ValueError("Not enough data to perform prediction")

    historical_prices = [pair.price for pair in trading_pairs]

    # Prepare the data for the LSTM model
    time_steps = 5
    X, y, scaler = prepare_data(historical_prices, time_steps)

    # Build and train the LSTM model
    model = build_lstm_model(time_steps)
    train_lstm_model(model, X, y, epochs=50)

    # Make predictions
    predicted_prices = make_predictions(model, X, scaler)

    return predicted_prices[-1]  # Return the latest predicted price


def predict_price_lstm_sqlalchemy(symbol: str):
    """
    Predict the next price for a given trading pair using an LSTM model from SQLAlchemy data.
    :param symbol: The trading pair symbol (e.g., BTC/USD)
    :return: Predicted next price
    """
    db: Session = SessionLocal()

    # Fetch historical prices for the symbol from the relational database
    trading_pairs = db.query(TradingPair).filter(TradingPair.symbol == symbol).order_by(TradingPair.id.desc()).limit(
        100).all()

    if len(trading_pairs) < 10:
        raise ValueError("Not enough data to perform prediction")

    historical_prices = [pair.price for pair in trading_pairs]

    # Prepare the data for the LSTM model
    time_steps = 5
    X, y, scaler = prepare_data(historical_prices, time_steps)

    # Build and train the LSTM model
    model = build_lstm_model(time_steps)
    train_lstm_model(model, X, y, epochs=50)

    # Make predictions
    predicted_prices = make_predictions(model, X, scaler)

    return predicted_prices[-1]  # Return the latest predicted price
