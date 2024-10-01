# trading_platform_backend/app/services/lstm_model.py

# LSTM model creation, training, and prediction logic

import numpy as np
import tensorflow as tf
from sklearn.preprocessing import MinMaxScaler

def prepare_data(prices, time_steps):
    """
    Prepare the dataset for LSTM, splitting it into features (X) and labels (y).
    :param prices: List of historical prices
    :param time_steps: Number of time steps to look back for predictions
    :return: Prepared data for training
    """
    prices = np.array(prices)
    scaler = MinMaxScaler(feature_range=(0, 1))
    prices_scaled = scaler.fit_transform(prices.reshape(-1, 1))

    X, y = [], []
    for i in range(time_steps, len(prices_scaled)):
        X.append(prices_scaled[i-time_steps:i, 0])
        y.append(prices_scaled[i, 0])

    return np.array(X), np.array(y), scaler

def build_lstm_model(time_steps):
    """
    Build an LSTM model for time-series forecasting.
    :param time_steps: Number of time steps to look back for predictions
    :return: Compiled LSTM model
    """
    model = tf.keras.models.Sequential()

    model.add(tf.keras.layers.LSTM(units=50, return_sequences=True, input_shape=(time_steps, 1)))
    model.add(tf.keras.layers.Dropout(0.2))  # Dropout for regularization

    model.add(tf.keras.layers.LSTM(units=50, return_sequences=False))
    model.add(tf.keras.layers.Dropout(0.2))

    model.add(tf.keras.layers.Dense(units=25))

    model.add(tf.keras.layers.Dense(units=1))  # Output layer

    model.compile(optimizer='adam', loss='mean_squared_error')

    return model

def train_lstm_model(model, X_train, y_train, epochs=10, batch_size=32):
    """
    Train the LSTM model on the provided training data.
    :param model: LSTM model
    :param X_train: Training features
    :param y_train: Training labels
    :param epochs: Number of epochs to train for
    :param batch_size: Size of each training batch
    """
    X_train = np.reshape(X_train, (X_train.shape[0], X_train.shape[1], 1))
    model.fit(X_train, y_train, epochs=epochs, batch_size=batch_size)

def make_predictions(model, X_test, scaler):
    """
    Make predictions using the trained LSTM model.
    :param model: Trained LSTM model
    :param X_test: Test data
    :param scaler: Scaler to inverse transform the predictions
    :return: Predicted prices
    """
    X_test = np.reshape(X_test, (X_test.shape[0], X_test.shape[1], 1))
    predictions = model.predict(X_test)
    predictions = scaler.inverse_transform(predictions)
    return predictions
