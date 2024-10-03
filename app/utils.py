# trading_platform_backend/app/utils.py

# Utility functions (e.g., for background tasks)

"""
TODO: High Frequency of Updates: Cryptocurrencies can be very volatile,
    leading to a high frequency of price updates. This is normal,
    but if you want to reduce the clutter in your output,
    consider implementing a throttling mechanism to limit how often you log updates
    for the same currency within a certain time frame.
"""
"""
TODO: implement a throttling mechanism to limit how often you log updates 
    for the same currency within a certain time frame.
"""
import asyncio
import websockets
import json
import time
import logging
from sqlalchemy.orm import Session
from app.models import TradingPair, MongoTradingPair
from contextlib import asynccontextmanager
# import aioredis
from redis.asyncio import Redis


logger = logging.getLogger(__name__)

REDIS_HOST = "localhost" # change to actual Redis server
REDIS_PORT = 6379
REDIS_DB = 0

# Global dictionary to hold the latest prices of trading pairs

latest_prices = {}
latest_prices_lock = asyncio.Lock()

# WebSocket URLs for different sources
BINANCE_WS_URL = "wss://stream.binance.com:9443/ws"
KRAKEN_WS_URL = "wss://ws.kraken.com"

# Mapping of symbols to our internal representation
WEBSOCKET_CURRENCY_PAIRS = {
    "btcusdt": "BTC",
    "ethusdt": "ETH",
    "ltcusdt": "LTC",
    "bnbusdt": "BNB",
    "xrpusdt": "XRP",
    "XBT/USD": "BTC",
    "ETH/USD": "ETH",
    "USD/KSH": "KES",
    "USD/UGX": "UGX",
    "EUR/USD": "USD",
    "USD/JPY": "JPY",
    "eurusd": "EUR/USD",
    "usdgbp": "USD/GBP",
    "usdjpy": "USD/JPY",
    "usdchf": "USD/CHF",
    "usdksh": "USD/KES"
}

# Dictionary to store the last update time for each symbol

last_update_times = {}


# Connect to Redis
async def get_redis_connection():
    return Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True)

async def set_cache(redis: Redis, key: str, value: str, expiration: int = 60):
    """
    Set the key-value pair in Redis with an optional expiration time.
    """
    await redis.set(key, value, ex=expiration)

async def get_cache(redis: Redis, key: str):
    """
    Get the value for a key from Redis.
    """
    return await redis.get(key)

async def should_update(symbol: str, interval: int = 2):
    """
    Determines whether a trading pair should be updated based on the throttling interval.
    :param symbol: Symbol of the trading pair
    :param interval: Minimum time interval between updates in seconds
    :return: Boolean indicating whether to update the price
    """
    current_time = time.time()
    last_update_time = last_update_times.get(symbol, 0)

    # Check if the current time exceeds the last update time plus the interval
    if current_time - last_update_time >= interval:
        last_update_times[symbol] = current_time
        return True
    return False

# Subscription message for Kraken WebSocket
def get_kraken_subscription_message():
    return json.dumps({
        "event": "subscribe",
        "pair": ["XBT/USD", "ETH/USD", "BTC/USD", "USD/KES", "USD/JPY", "EUR/USD" "USD/UGX"],  # pairs to subscribe to
        "subscription": {
            "name": "ticker"  # Subscribe to ticker updates
        }
    })

# Subscription message for Binance WebSocket
def get_binance_subscription_message():
    return json.dumps({
        "method": "SUBSCRIBE",
        "params": [
            "btcusdt@trade",
            "ethusdt@trade",
            "ltcusdt@trade",
            "bnbusdt@trade",
            "xrpusdt@trade"
        ],
        "id": 1
    })

async def send_pings(websocket, interval=30):
    """
    Send pings at regular intervals to keep the WebSocket connection alive.
    :param websocket: The WebSocket connection
    :param interval: Ping interval in seconds
    """
    while True:
        await asyncio.sleep(interval)
        try:
            pong_waiter = await websocket.ping()
            await asyncio.wait_for(pong_waiter, timeout=30)  # Wait for the pong message with a timeout
            logger.info("Ping successful!")
        except asyncio.TimeoutError:
            logger.error("Ping timed out. Connection might be unstable.")
            break
        except Exception as e:
            logger.error(f"Failed to send ping: {e}")
            break

async def reconnect_with_backoff(url, subscription_message, db_session):
    """
    Reconnect to the WebSocket with exponential backoff on connection failures.
    :param url: WebSocket URL to connect to
    :param subscription_message: The message to send to subscribe to the WebSocket updates
    :param db_session: SQLAlchemy session for database interaction
    """
    delay = 2  # Initial delay in seconds
    max_delay = 60  # Maximum delay in seconds
    while True:
        try:
            # Create a new WebSocket connection
            websocket = await websockets.connect(url, ping_interval=500, ping_timeout=30)
            logger.info(f"Connected to WebSocket at {url} and subscribing to currency pairs.")
            await websocket.send(subscription_message)
            asyncio.create_task(send_pings(websocket, interval=120))  # Start sending pings

            # Listen for messages
            while True:
                message = await websocket.recv()
                await handle_message(message, db_session)

        except websockets.exceptions.ConnectionClosed as e:
            logger.error(f"Connection closed: {e}. Retrying in {delay} seconds...")
        except Exception as e:
            logger.error(f"Failed to connect to WebSocket: {e}. Retrying in {delay} seconds...")

        await asyncio.sleep(delay)
        delay = min(delay * 2, max_delay)  # Exponential backoff


async def handle_message(message, db_session):
    """
    Handle incoming WebSocket messages and update trading pairs in the database.
    :param message: The WebSocket message
    :param db_session: SQLAlchemy session for database interaction
    """
    try:
        data = json.loads(message)
        # print(f"Received message: {data}")  # Debug print to inspect the structure of the message

        # Handle Binance messages: They usually come as a dictionary
        if isinstance(data, dict) and data.get("e") == "trade":  # Filter for trade events
            symbol = data["s"].lower()  # Trading pair symbol (e.g., 'ETHUSDT')
            price = float(data["p"])  # Latest price
            if symbol in WEBSOCKET_CURRENCY_PAIRS:
                mapped_symbol = WEBSOCKET_CURRENCY_PAIRS[symbol]
                if await should_update(mapped_symbol):
                    async with latest_prices_lock:
                        latest_prices[mapped_symbol] = price
                    await update_or_create_trading_pair(db_session, mapped_symbol, price)

        # Handle Kraken messages: These usually come as a list
        elif isinstance(data, list) and len(data) > 1 and isinstance(data[1], dict):
            pair = data[3]  # The trading pair (e.g., XBT/USD)
            price = float(data[1]['c'][0])  # Current price from the response
            mapped_symbol = WEBSOCKET_CURRENCY_PAIRS.get(pair)
            if mapped_symbol:
                if await should_update(mapped_symbol):
                    async with latest_prices_lock:
                        latest_prices[mapped_symbol] = price
                    await update_or_create_trading_pair(db_session, mapped_symbol, price)

    except Exception as e:
        logger.error(f"Error handling message: {e}")


async def binance_websocket_listener(db_session):
    """
    Binance WebSocket listener for receiving real-time price updates.
    :param db_session: SQLAlchemy session for database interaction
    """
    await reconnect_with_backoff(BINANCE_WS_URL, get_binance_subscription_message(), db_session)

async def kraken_websocket_listener(db_session):
    """
    Kraken WebSocket listener for receiving real-time price updates.
    :param db_session: SQLAlchemy session for database interaction
    """
    await reconnect_with_backoff(KRAKEN_WS_URL, get_kraken_subscription_message(), db_session)

async def fetch_real_time_prices(db_session: Session):
    """
    Fetch real-time prices for cryptocurrencies and fiat currencies using WebSocket connections.
    :param db_session: SQLAlchemy session for database interaction
    """
    await asyncio.gather(
        binance_websocket_listener(db_session),
        kraken_websocket_listener(db_session)
    )


async def update_or_create_trading_pair(db: Session, symbol: str, price: float):
    """
    Update the trading pair in both SQLAlchemy (relational) and MongoDB (NoSQL) databases.
    :param db: SQLAlchemy session
    :param symbol: Symbol of the trading pair (e.g., BTC, EUR/USD)
    :param price: Latest price of the trading pair
    """
    try:
        # Update or create in SQLAlchemy
        trading_pair = db.query(TradingPair).filter(TradingPair.symbol == symbol).first()

        if trading_pair:
            trading_pair.price = price
        else:
            trading_pair = TradingPair(symbol=symbol, price=price)
            db.add(trading_pair)
        db.commit()
        db.refresh(trading_pair)  # Refresh the updated trading pair

        # Update or create in MongoDB (Beanie)
        mongo_trading_pair = await MongoTradingPair.find_one(MongoTradingPair.symbol == symbol)
        if mongo_trading_pair:
            mongo_trading_pair.price = price
            await mongo_trading_pair.save()
        else:
            mongo_trading_pair = MongoTradingPair(symbol=symbol, price=price)
            await mongo_trading_pair.insert()

    except Exception as e:
        db.rollback()
        logger.error(f"Error occurred while updating/creating trading pair {symbol}: {e}")