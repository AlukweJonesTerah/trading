# trading_platform_backend/app/services/trading_service.py

# Logic related to placing bets and evaluating outcomes

from sqlalchemy.orm import Session
from beanie import PydanticObjectId
from app.models import TradingPair, Order, User, MongoOrder, MongoUser, MongoTradingPair
from fastapi import HTTPException
from datetime import datetime
import asyncio
from app.schemas import OrderCreate
from app.database import Base, engine, SessionLocal
from app.utils import latest_prices

MIN_TRADE_AMOUNT = 10.0  # Minimum trade amount in dollars
MAX_TRADE_AMOUNT = 1000.0  # Maximum trade amount in dollars
VALID_TRADE_TIMES = [30, 60, 90, 120, 150, 180, 210, 240, 270, 300]  # 30 seconds to 5 minutes
VALID_CURRENCY_TYPES = ["BTC", "ETH", "LTC", "XRP", "BNB"]


def validate_trade(order: OrderCreate):
    if order.amount < MIN_TRADE_AMOUNT:
        raise HTTPException(status_code=400,
                            detail=f"Trade amount too low. Minimum trade amount is ${MIN_TRADE_AMOUNT}.")

    if order.amount > MAX_TRADE_AMOUNT:
        raise HTTPException(status_code=400,
                            detail=f"Trade amount too high. Maximum trade amount is ${MAX_TRADE_AMOUNT}.")

    if order.trade_time not in VALID_TRADE_TIMES:
        raise HTTPException(status_code=400,
                            detail="Invalid trade time. It must be between 30 seconds and 5 minutes, in 30-second "
                                   "intervals.")

    if order.symbol not in VALID_CURRENCY_TYPES:
        raise HTTPException(status_code=400, detail="Invalid currency type.")


async def place_order_mongo(order: OrderCreate, user_id: str):
    # Get the trading pair from MongoDB
    trading_pair = await MongoTradingPair.find_one(MongoTradingPair.symbol == order.symbol)
    if not trading_pair:
        print(f"Trading pair {order.symbol} not found in MongoDB.")
        raise HTTPException(status_code=404, detail="Trading pair not found")

    # Get the user from MongoDB
    user = await MongoUser.get(PydanticObjectId(user_id))
    if not user or user.balance < order.amount:
        raise HTTPException(status_code=400, detail="Insufficient balance")

    # Lock the price and deduct the amount
    locked_price = trading_pair.price
    user.balance -= order.amount
    await user.save()

    # Create the order
    mongo_order = MongoOrder(
        user_id=user.id,
        symbol=order.symbol,
        amount=order.amount,
        prediction=order.prediction,
        trade_time=order.trade_time,
        locked_price=locked_price,
        start_time=datetime.utcnow(),
        status="pending"
    )
    await mongo_order.insert()

    # Schedule outcome evaluation
    schedule_evaluation(mongo_order.trade_time, mongo_order.id)

    # return mongo_order
    # Return the order data with the id field
    return {
        "id": str(mongo_order.id),  # convert id to string
        "user_id": str(mongo_order.user_id),
        "symbol": mongo_order.symbol,
        "amount": mongo_order.amount,
        "prediction": mongo_order.prediction,
        "trade_time": mongo_order.trade_time,
        "locked_price": mongo_order.locked_price,
        "start_time": mongo_order.start_time,
        "status": mongo_order.status
    }

def place_order_sqlalchemy(db: Session, order: OrderCreate, user_id: int):
    # Get the trading pair from SQLAlchemy
    trading_pair = db.query(TradingPair).filter(TradingPair.symbol == order.symbol).first()
    if not trading_pair:
        print(f"Trading pair {order.symbol} not found in SQLAlchemy.")
        raise HTTPException(status_code=404, detail="Trading pair not found")

    # Get the user from SQLAlchemy
    user = db.query(User).filter(User.id == user_id).first()
    if not user or user.balance < order.amount:
        raise HTTPException(status_code=400, detail="Insufficient balance")

    # Lock the price and deduct the amount
    locked_price = trading_pair.price
    user.balance -= order.amount
    db.commit()

    # Create the order in SQLAlchemy
    db_order = Order(
        user_id=user.id,
        symbol=order.symbol,
        amount=order.amount,
        prediction=order.prediction,
        trade_time=order.trade_time,
        locked_price=locked_price,
        start_time=datetime.utcnow(),
        status="pending"
    )
    db.add(db_order)
    db.commit()
    db.refresh(db_order)

    # Schedule outcome evaluation
    schedule_evaluation(db_order.trade_time, db_order.id, db)

    # return db_order
    # Return the order data with the id field
    return {
        "id": db_order.id,  # Make sure the id is included
        "user_id": db_order.user_id,
        "symbol": db_order.symbol,
        "amount": db_order.amount,
        "prediction": db_order.prediction,
        "trade_time": db_order.trade_time,
        "locked_price": db_order.locked_price,
        "start_time": db_order.start_time,
        "status": db_order.status
    }



def evaluate_order_outcome_sqlalchemy(order_id: int, db: Session):
    # Fetch the order from SQLAlchemy
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order or order.status != "pending":
        return

    # Get the current price of the trading pair
    trading_pair = db.query(TradingPair).filter(TradingPair.symbol == order.symbol).first()
    if not trading_pair:
        return

    final_price = trading_pair.price

    # Determine if the prediction was correct
    if order.prediction == "rise" and final_price > order.locked_price:
        order.status = "win"
        payout = order.amount * 1.02  # 2% payout for correct prediction
        order.user.balance += payout
    elif order.prediction == "fall" and final_price < order.locked_price:
        order.status = "win"
        payout = order.amount * 1.02
        order.user.balance += payout
    else:
        order.status = "lose"

    db.commit()


async def evaluate_order_outcome_mongo(order_id: PydanticObjectId):
    # Fetch the order from MongoDB
    order = await MongoOrder.get(order_id)
    if not order or order.status != "pending":
        return

    # Get the current price of the trading pair
    trading_pair = await MongoTradingPair.find_one(MongoTradingPair.symbol == order.symbol)
    if not trading_pair:
        return

    final_price = trading_pair.price

    # Determine if the prediction was correct
    if order.prediction == "rise" and final_price > order.locked_price:
        order.status = "win"
        payout = order.amount * 1.02  # 2% payout for correct prediction
        user = await MongoUser.get(order.user_id)
        user.balance += payout
        await user.save()
    elif order.prediction == "fall" and final_price < order.locked_price:
        order.status = "win"
        payout = order.amount * 1.02
        user = await MongoUser.get(order.user_id)
        user.balance += payout
        await user.save()
    else:
        order.status = "lose"

    await order.save()


async def place_order_with_real_time_price(order: OrderCreate, user_id: str): # , user_id: str
    # Validate trade
    validate_trade(order)

    # Get the real-time price for the trading pair
    if order.symbol not in latest_prices:
        raise HTTPException(status_code=404, detail="Real-time price not available for the trading pair.")

    locked_price = latest_prices[order.symbol]

    # Lock the price and proceed with placing the order (you can add user balance checks here)
    order_data = {
        "user_id": PydanticObjectId(user_id),
        "symbol": order.symbol,
        "amount": order.amount,
        "prediction": order.prediction,
        "trade_time": order.trade_time,
        "locked_price": locked_price,
        "start_time": datetime.utcnow(),
        "status": "pending"
    }

    # inserting the order into the database (MongoDB, SQLAlchemy)
    # return order_data

    # Simulate inserting the order into MongoDB or SQLAlchemy and returning an id
    mongo_order = MongoOrder(**order_data)
    await mongo_order.insert()

    # Simulate the order being processed with real-time price
    print(f"Order placed: {order_data}")

    # Schedule outcome evaluation
    schedule_evaluation(mongo_order.trade_time, str(mongo_order.id))

    # Return the order data with the id
    return {
        "id": str(mongo_order.id),  # Ensure the id is returned
        "user_id": str(mongo_order.user_id),
        "symbol": mongo_order.symbol,
        "amount": mongo_order.amount,
        "prediction": mongo_order.prediction,
        "trade_time": mongo_order.trade_time,
        "locked_price": mongo_order.locked_price,
        "start_time": mongo_order.start_time,
        "status": mongo_order.status
    }

async def evaluate_order_outcome_with_real_time_price(order_id: str):
    """
    Evaluates the outcome of an order based on real-time prices without database storage.
    :param order_id: The ID of the order to evaluate.
    """

    # Fetch the order from MongoDB using the order_id
    order = await MongoOrder.get(PydanticObjectId(order_id))
    if not order or order.status != "pending":
        print(f"Order {order_id} not found or not pending.")
        return

    # Get the real-time price of the trading pair from `latest_prices`
    if order.symbol not in latest_prices:
        print(f"Real-time price for {order.symbol} not found.")
        return

    final_price = latest_prices[order.symbol]

    print(f"Evaluating order {order_id} with final price {final_price} and locked price {order.locked_price}")

    # Determine if the prediction was correct and update order status
    if order.prediction == "rise" and final_price > order.locked_price:
        order.status = "win"
        payout = order.amount * 1.02  # 2% payout for correct prediction
        user = await MongoUser.get(order.user_id)
        user.balance += payout
        await user.save()
        print(f"Order {order_id}: User won! Final price: {final_price}, Locked price: {order.locked_price}.")
    elif order.prediction == "fall" and final_price < order.locked_price:
        order.status = "win"
        payout = order.amount * 1.02
        user = await MongoUser.get(order.user_id)
        user.balance += payout
        await user.save()
        print(f"Order {order_id}: User won! Final price: {final_price}, Locked price: {order.locked_price}.")
    else:
        order.status = "lose"
        print(f"Order {order_id}: User lost. Final price: {final_price}, Locked price: {order.locked_price}.")

    # Save the updated order status
    await order.save()

    print(f"Order {order_id} evaluated with real-time price: {final_price}, Status: {order.status}")

def schedule_evaluation(trade_time: int, order_id: str, db=None, real_time=False):
    """
    Schedules the evaluation of the order outcome after trade_time seconds.
    This is handled asynchronously using asyncio to wait for the duration and then evaluate.
    """
    async def evaluate():
        await asyncio.sleep(trade_time)  # Wait for the specified trade time
        if db:
            evaluate_order_outcome_sqlalchemy(order_id, db)
        elif real_time:
            print(f"Scheduling evaluation for order {order_id} after {trade_time} seconds.")
            await asyncio.sleep(trade_time)  # Wait for the specified trade time
            await evaluate_order_outcome_with_real_time_price(order_id)
        else:
            await evaluate_order_outcome_mongo(order_id)

    # evaluation is scheduled as a background task
    asyncio.create_task(evaluate())
