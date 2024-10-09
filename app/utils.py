import asyncio
import websockets
import json
import time
import logging
import requests

from beanie import PydanticObjectId
from cachetools import TTLCache
from app.models import MongoTradingPair

logger = logging.getLogger(__name__)

# TTLCache Configuration
price_cache = TTLCache(maxsize=10000, ttl=30)
last_update_times = TTLCache(maxsize=10000, ttl=2)  # Store last update times with a short TTL of 2 seconds

# Dictionary to store the last update time for each symbol
last_update_times = {}

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

# Lock for managing concurrent access to `price_cache`
cache_lock = asyncio.Lock()


async def should_update(symbol: str, interval: int = 2):
    """
    Determines whether a trading pair should be updated based on the throttling interval.
    :param symbol: Symbol of the trading pair
    :param interval: Minimum time interval between updates in seconds
    :return: Boolean indicating whether to update the price
    """
    current_time = time.time()
    last_update_time = last_update_times.get(symbol, 0)

    if last_update_time is None or current_time - last_update_time >= interval:
        last_update_times[symbol] = current_time
        return True

    return False


def get_kraken_subscription_message():
    return json.dumps({
        "event": "subscribe",
        "pair": ["XBT/USD", "ETH/USD", "BTC/USD", "USD/KES", "USD/JPY", "EUR/USD", "USD/UGX"],
        "subscription": {
            "name": "ticker"
        }
    })


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


async def reconnect_with_backoff(url, subscription_message):
    """
    Reconnect to the WebSocket with exponential backoff on connection failures.
    :param url: WebSocket URL to connect to
    :param subscription_message: The message to send to subscribe to the WebSocket updates
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
                await handle_message(message)

        except websockets.exceptions.ConnectionClosed as e:
            logger.error(f"Connection closed: {e}. Retrying in {delay} seconds...")
            await asyncio.sleep(delay)
            delay = min(delay * 2, max_delay)
        except Exception as e:
            logger.error(f"Failed to connect to WebSocket: {e}. Retrying in {delay} seconds...")
            await asyncio.sleep(delay)
            delay = min(delay * 2, max_delay)


async def handle_message(message):
    """
    Handle incoming WebSocket messages and update trading pairs in the database.
    :param message: The WebSocket message
    """
    try:
        data = json.loads(message)

        # Handle Binance messages: They usually come as a dictionary
        if isinstance(data, dict) and data.get("e") == "trade":  # Filter for trade events
            symbol = data["s"].lower()
            price = float(data["p"])
            if symbol in WEBSOCKET_CURRENCY_PAIRS:
                mapped_symbol = WEBSOCKET_CURRENCY_PAIRS[symbol]
                if await should_update(mapped_symbol):
                    async with cache_lock:
                        price_cache[mapped_symbol] = price

                    async with latest_prices_lock:
                        latest_prices[mapped_symbol] = price
                    await update_or_create_trading_pair(mapped_symbol, price)

        # Handle Kraken messages
        elif isinstance(data, list) and len(data) > 1 and isinstance(data[1], dict):
            pair = data[3]  # The trading pair (e.g., XBT/USD)
            price = float(data[1]['c'][0])  # Current price from the response
            mapped_symbol = WEBSOCKET_CURRENCY_PAIRS.get(pair)
            if mapped_symbol:
                if await should_update(mapped_symbol):
                    async with cache_lock:
                        price_cache[mapped_symbol] = price

                    async with latest_prices_lock:
                        latest_prices[mapped_symbol] = price
                    await update_or_create_trading_pair(mapped_symbol, price)

    except Exception as e:
        logger.error(f"Error handling message: processing WebSocket message: {e}")


async def binance_websocket_listener():
    """
    Binance WebSocket listener for receiving real-time price updates.
    """
    await reconnect_with_backoff(BINANCE_WS_URL, get_binance_subscription_message())


async def kraken_websocket_listener():
    """
    Kraken WebSocket listener for receiving real-time price updates.
    """
    await reconnect_with_backoff(KRAKEN_WS_URL, get_kraken_subscription_message())


async def fetch_real_time_prices(*args, **kwargs):
    """
    Fetch real-time prices for cryptocurrencies and fiat currencies using WebSocket connections.
    """
    await asyncio.gather(
        binance_websocket_listener(),
        kraken_websocket_listener(),
        # fetch_http_prices()
    )


COINGECKO_API_URL = "https://api.coingecko.com/api/v3/simple/price?"


async def fetch_http_prices():
    """
    Fetch real-time prices using an HTTP API as a fallback when WebSocket fails.
    """
    symbols = ["bitcoin", "ethereum", "litecoin", "binancecoin", "ripple"]
    params = {
        "ids": ",".join(symbols),
        "vs_currencies": "usd"
    }
    try:
        response = requests.get(COINGECKO_API_URL, params=params)
        if response.status_code == 200:
            data = response.json()
            for symbol, price_data in data.items():
                price = price_data['usd']
                mapped_symbol = WEBSOCKET_CURRENCY_PAIRS.get(f"{symbol}usd", None)
                if mapped_symbol:
                    latest_prices[mapped_symbol] = price
                    await update_or_create_trading_pair(mapped_symbol, price)
            logger.info(f"Prices fetched via HTTP fallback: {latest_prices}")
        else:
            logger.error(f"HTTP fallback failed with status code: {response.status_code}")
    except Exception as e:
        logger.error(f"Failed to fetch prices via HTTP: {e}")


async def update_or_create_trading_pair(symbol: str, price: float):
    """
    Update the trading pair in MongoDB.
    :param symbol: Symbol of the trading pair (e.g., BTC, EUR/USD)
    :param price: Latest price of the trading pair
    """
    try:
        mongo_trading_pair = await MongoTradingPair.find_one(MongoTradingPair.symbol == symbol)
        if mongo_trading_pair:
            mongo_trading_pair.price = price
            await mongo_trading_pair.save()
        else:
            mongo_trading_pair = MongoTradingPair(symbol=symbol, price=price)
            await mongo_trading_pair.insert()
        logger.info(f"Updated/created trading pair {symbol} with price {price}.")
    except Exception as e:
        logger.error(f"Failed to update or create trading pair {symbol}: {e}")
