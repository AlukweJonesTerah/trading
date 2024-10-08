import asyncio
import logging
import re
from datetime import datetime
from typing import Optional

from beanie import PydanticObjectId
from cachetools import TTLCache
from fastapi import HTTPException

from app.models import MongoOrder, MongoUser
from app.schemas import OrderCreate
from app.utils import latest_prices

# Configure TTLCache with a maxsize of 1000 and TTL of 60 seconds for each price entry
price_cache = TTLCache(maxsize=10000, ttl=30)

# Mock shared state for real-time prices (replace this with your actual implementation)
# latest_prices: Dict[str, float] = {}
latest_prices_lock = asyncio.Lock()  # Asynchronous lock for safely accessing `latest_prices`

logger = logging.getLogger(__name__)

MAX_PENDING_ORDERS = 3  # Maximum allowed pending orders per user
MIN_TRADE_AMOUNT = 10.0  # Minimum trade amount in dollars
MAX_TRADE_AMOUNT = 1000.0  # Maximum trade amount in dollars
VALID_TRADE_TIMES = [30, 60, 90, 120, 150, 180, 210, 240, 270, 300]  # 30 seconds to 5 minutes
VALID_CURRENCY_TYPES = ["BTC", "ETH", "LTC", "XRP", "BNB", "KES", "USD", "JPY", "EUR"]


# Function to validate the trade based on system's trading rules
def validate_trade(order: OrderCreate):
    # Convert the prediction to lowercase before validation
    order.prediction = order.prediction.lower()

    # Ensure the prediction matches 'rise' or 'fall'
    if not re.match(r"^(rise|fall)$", order.prediction):
        raise HTTPException(
            status_code=400,
            detail={"message": "Prediction must be either 'rise' or 'fall'.",
                    "hint": "Check the casing and spelling of the 'prediction' field.",
                    "valid_values": ["rise", "fall"],
                    "input_received": order.predictio
                    }
        )

    if order.amount < MIN_TRADE_AMOUNT:
        logger.error(f"Trade amount too low. Minimum trade amount is ${MIN_TRADE_AMOUNT}.")
        raise HTTPException(status_code=400,
                            detail=f"Trade amount too low. Minimum trade amount is ${MIN_TRADE_AMOUNT}.")

    if order.amount > MAX_TRADE_AMOUNT:
        logger.error(f"Trade amount too high. Maximum trade amount is ${MAX_TRADE_AMOUNT}.")
        raise HTTPException(status_code=400,
                            detail=f"Trade amount too high. Maximum trade amount is ${MAX_TRADE_AMOUNT}.")

    if order.trade_time not in VALID_TRADE_TIMES:
        logger.error("Invalid trade time. It must be between 30 seconds and 5 minutes, in 30-second intervals.")
        raise HTTPException(status_code=400,
                            detail="Invalid trade time. It must be between 30 seconds and 5 minutes, in 30-second "
                                   "intervals.")

    if order.symbol not in VALID_CURRENCY_TYPES:
        logger.error("Invalid currency type.")
        raise HTTPException(status_code=400, detail="Invalid currency type.")


async def count_pending_orders_for_user(user_id: str) -> int:
    """
    Count how many pending orders a user currently has in the system.
    """
    return await MongoOrder.find({"user_id": PydanticObjectId(user_id), "status": "pending"}).count()


async def place_order_with_real_time_price(order: OrderCreate, user_id: Optional[str] = None):  # , user_id: str
    """
    Place an order with the current real-time price for the trading pair.
    If no user_id is provided, a temporary user ID will be used.
    """

    # Use a temporary user ID if none is provided

    if user_id is None:
        user_id = "6706b0b9571ca603c9868674"  # Temporary user ID

    # Validate trade data
    try:
        validate_trade(order)
    except HTTPException as e:
        logger.error(f"Trade validation failed: {e.detail}")
        raise e

    # Acquire the latest prices safely using a lock to avoid race conditions
    async with latest_prices_lock:
        if order.symbol not in latest_prices:
            raise HTTPException(status_code=404, detail="Real-time price not available for the trading pair.")
        locked_price = latest_prices[order.symbol]

    # fecting the user to updated his/her balance
    user = await MongoUser.get(PydanticObjectId(user_id))

    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    # check if the user has enough balance in account to allow betting
    if user.balance < order.amount:
        raise HTTPException(status_code=400, detail="Insufficient balance to place the order")

    # make deduction of order amount from the user's balance
    user.balance -= order.amount
    await user.save()  # save the new updated useer's balnce

    # Lock the price and proceed with placing the order
    order_data = {
        "user_id": PydanticObjectId(user_id),
        "symbol": order.symbol,
        "amount": order.amount,
        "prediction": order.prediction,
        "trade_time": order.trade_time,
        "locked_price": locked_price,
        "start_time": datetime.utcnow(),
        "status": "pending",
    }

    # Insert the order into the MongoDB collection
    mongo_order = MongoOrder(**order_data)
    await mongo_order.insert()
    print(f"Order placed: {order_data}")

    # Schedule the order evaluation after the specified trade time
    schedule_evaluation(mongo_order.trade_time, str(mongo_order.id))

    # Return the order data with the ID
    return {
        "id": str(mongo_order.id),
        "user_id": str(mongo_order.user_id),
        "symbol": mongo_order.symbol,
        "amount": mongo_order.amount,
        "prediction": mongo_order.prediction,
        "trade_time": mongo_order.trade_time,
        "locked_price": mongo_order.locked_price,
        "start_time": mongo_order.start_time,
        "status": mongo_order.status,
    }


async def evaluate_order_outcome_with_real_time_price(order_id: str):
    """
    Evaluates the outcome of an order based on real-time prices without blocking the WebSocket connection.
    """
    print(f"Starting evaluation for order {order_id}...")

    try:
        # Fetch the order from MongoDB
        order = await MongoOrder.get(PydanticObjectId(order_id))
        if not order:
            print(f"Order {order_id} not found.")
            return

        if order.status != "pending":
            print(f"Order {order_id} is no longer pending (status: {order.status}).")
            return

        # Acquire latest prices safely
        async with latest_prices_lock:
            if order.symbol not in latest_prices:
                print(f"Real-time price for {order.symbol} not found.")
                return
            final_price = latest_prices[order.symbol]

        print(f"Evaluating order {order_id} with final price {final_price} and locked price {order.locked_price}")

        # Fetch the user from MongoDB
        user = await MongoUser.get(order.user_id)
        if not user:
            print(f"User with ID {order.user_id} not found.")
            return

        payout = 0

        # Determine if the prediction was correct and update order status
        if order.prediction == "rise" and final_price > order.locked_price:
            order.status = "win"
            payout = order.amount * 1.02  # 2% payout for correct prediction
            order.payout = payout  # setting payout value
            print(f"Order {order_id}: User won! Final price: {final_price}, Locked price: {order.locked_price}.")

            # Update user's balance
            user.balance += payout
        elif order.prediction == "fall" and final_price < order.locked_price:
            order.status = "win"
            payout = order.amount * 1.02
            order.payout = payout
            print(f"Order {order_id}: User won! Final price: {final_price}, Locked price: {order.locked_price}.")

            # Update user's balance
            user.balance += payout
        else:
            order.status = "lose"
            order.payout = 0  # setting payout to 0 (zero) if the user loses
            print(f"Order {order_id}: User lost. Final price: {final_price}, Locked price: {order.locked_price}.")

        # Save the updated order status and user balance in a non-blocking way
        await order.save()
        await user.save()
        print(f"Order {order_id} evaluated with real-time price: {final_price}, Status: {order.status}")

    except Exception as e:
        print(f"Error evaluating order {order_id}: {e}")


def schedule_evaluation(trade_time: int, order_id: str):
    """
    Schedules the evaluation of the order outcome after trade_time seconds.
    """

    async def evaluate():
        await asyncio.sleep(trade_time)  # Wait for the specified trade time
        await evaluate_order_outcome_with_real_time_price(order_id)

    # Schedule evaluation as a background task
    asyncio.create_task(evaluate())
