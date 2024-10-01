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
from sqlalchemy.orm import Session
from app.models import TradingPair, MongoTradingPair
import time


# WebSocket URLs for different sources
BINANCE_WS_URL = "wss://stream.binance.com:9443/ws"
KRAKEN_WS_URL = "wss://ws.kraken.com"  # Corrected Kraken WebSocket URL for real-time data

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

async def should_update(symbol: str, interval: int = 3):
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
        "pair": ["XBT/USD", "ETH/USD"],  # Specify the pairs you want to subscribe to
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
    while True:
        await asyncio.sleep(interval)
        try:
            pong_waiter = await websocket.ping()
            await asyncio.wait_for(pong_waiter, timeout=10)  # Wait for the pong message with a timeout
            print("Ping successful!")
        except asyncio.TimeoutError:
            print("Ping timed out. Connection might be unstable.")
            break
        except Exception as e:
            print(f"Failed to send ping: {e}")
            break

# Global dictionary to store the latest prices
latest_prices = {}

async def fetch_real_time_prices(db_session):
    """
    Fetch real-time prices for cryptocurrencies and fiat currencies
    using WebSocket connections.
    """

    async def binance_websocket_listener():
        while True:
            try:
                async with websockets.connect(BINANCE_WS_URL, ping_interval=30, ping_timeout=10) as websocket:
                    await websocket.send(get_binance_subscription_message())
                    print("Connected to Binance WebSocket and subscribed to crypto trading pairs.")

                    # Start a background task to send pings for keep-alive
                    asyncio.create_task(send_pings(websocket))

                    while True:
                        message = await websocket.recv()
                        data = json.loads(message)

                        if data.get("e") == "trade":
                            symbol = data["s"].lower()
                            price = float(data["p"])
                            if symbol in WEBSOCKET_CURRENCY_PAIRS:
                                mapped_symbol = WEBSOCKET_CURRENCY_PAIRS[symbol]
                                # throttling
                                if await should_update(mapped_symbol):
                                    # print(f"Binance update for {mapped_symbol}: {price}")
                                    latest_prices[mapped_symbol] = price
                                    # print(f"Binance update for {latest_prices}")
                                    await update_or_create_trading_pair(db_session, mapped_symbol, price)

            except websockets.exceptions.ConnectionClosed as e:
                print(f"Connection closed: {e}. Attempting to reconnect...")
                await asyncio.sleep(5)  # Wait before reconnecting
            except OSError as e:
                print(f"OSError: {e}. Retrying connection...")
                await asyncio.sleep(5)
            except Exception as e:
                print(f"Failed to connect to Binance WebSocket: {e}. Retrying...")
                await asyncio.sleep(5)  # Wait before trying again

    async def kraken_websocket_listener():
        while True:
            try:
                async with websockets.connect(KRAKEN_WS_URL, ping_interval=30, ping_timeout=10) as websocket:
                    print("Connected to Kraken WebSocket and subscribing to currency pairs.")
                    await websocket.send(get_kraken_subscription_message())

                    # Start a background task to send pings for keep-alive
                    asyncio.create_task(send_pings(websocket))

                    while True:
                        message = await websocket.recv()
                        data = json.loads(message)

                        if isinstance(data, list) and len(data) > 1 and isinstance(data[1], dict):
                            pair = data[3]  # The trading pair (e.g., XBT/USD)
                            price = data[1]['c'][0]  # Current price from the response
                            mapped_symbol = WEBSOCKET_CURRENCY_PAIRS.get(pair)
                            if mapped_symbol:
                                # throttling
                                if await should_update(mapped_symbol):
                                    # print(f"Kraken update for {mapped_symbol}: {price}")
                                    latest_prices[mapped_symbol] = price
                                    # print(f"Kraken update for {latest_prices}")
                                    await update_or_create_trading_pair(db_session, mapped_symbol, price)

            except websockets.exceptions.ConnectionClosed as e:
                print(f"Connection closed: {e}. Attempting to reconnect...")
                await asyncio.sleep(5)  # Wait before reconnecting
            except OSError as e:
                print(f"OSError: {e}. Retrying connection...")
                await asyncio.sleep(5)  # Wait before trying again
            except Exception as e:
                print(f"Failed to connect to Kraken WebSocket: {e}. Retrying...")
                await asyncio.sleep(5)  # Wait before trying again

    # Start both listeners
    await asyncio.gather(binance_websocket_listener(), kraken_websocket_listener())


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
            # Update the existing trading pair's price
            trading_pair.price = price
        else:
            # Create a new trading pair
            trading_pair = TradingPair(symbol=symbol, price=price)
            db.add(trading_pair)
        # Commit the changes
        db.commit()
        db.refresh(trading_pair) # Refresh the updated trading pair


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
        print(f"Error occurred while updating/creating trading pair {symbol}: {e}")
