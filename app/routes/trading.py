# trading_platform_backend/app/routes/trading.py

# Routes for handling trading logic

import asyncio
import logging
from datetime import datetime, timedelta, date
from typing import List, Dict, Optional

from beanie import PydanticObjectId
from bson import ObjectId
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, HTTPException

from app.models import MongoTradingPair, MongoUser, MongoOrder
from app.schemas import OrderCreate, OrderResponse
from app.services import trading_service
from app.utils import fetch_real_time_prices

router = APIRouter()

logger = logging.getLogger(__name__)


@router.websocket("/ws/prices")  # should use web socket URL
async def websocket_prices(websocket: WebSocket):
    """
    TODO create Rest api
    :param websocket:
    :return:
    """
    await websocket.accept()
    try:
        while True:
            prices = await fetch_real_time_prices()
            await websocket.send_json(prices)
            await asyncio.sleep(1)  # Send updates every second
    except WebSocketDisconnect:
        pass


# Dummy function to simulate getting a user without authentication
async def get_dummy_user():
    try:
        # Attempt to fetch an existing dummy user or create a new one
        dummy_user = await MongoUser.find_one(MongoUser.username == "dummy_user")
        if not dummy_user:
            # Create a new dummy user if not found
            dummy_user = MongoUser(
                username="dummy_user",
                email="dummy@example.com",
                hashed_password="hashed_test_pwd",  # Normally you would hash this password
                balance=1000.0,
                is_active=True
            )
            await dummy_user.insert()
        return dummy_user
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create or retrieve dummy user: {str(e)}")


@router.post("/api/trades/place_order", response_model=OrderResponse)
async def place_order(order: OrderCreate):  # , user_id: str = Depends(get_current_user_id)
    """
    Endpoint to place an order with the current real-time price for the trading pair.
    """
    logger.info("Received order placement request.")
    try:
        # Place the order with real-time price and return the response
        order_response = await trading_service.place_order_with_real_time_price(order)  # , user_id
        return order_response
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Failed to place order: {e}")
        print(f"Error placing order: {e}")
        raise HTTPException(status_code=500, detail="An unexpected error occurred while placing the order.")


@router.get("/trades/real_time", response_model=dict)
async def get_real_time_prices_endpoint():
    """
    Endpoint to fetch real-time prices for cryptocurrencies and fiat currencies directly from external APIs
    without saving them to the database.
    """
    prices = await fetch_real_time_prices()
    if not prices:
        raise HTTPException(status_code=500, detail="Failed to fetch real-time prices.")
    return prices


@router.get("/trading_pairs/mongo")
async def get_mongo_trading_pairs():
    trading_pairs = await MongoTradingPair.find_all().to_list()
    return [{"symbol": pair.symbol, "price": pair.price} for pair in trading_pairs]


@router.get("/balance", response_model=dict)
async def get_user_balance():
    # Replace with the appropriate user session or user fetching logic
    user = await MongoUser.get(PydanticObjectId("6706b0b9571ca603c9868674"))  # Hardcoded for now
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return {"balance": user.balance}


@router.get("/{order_id}", response_model=OrderResponse)
async def get_order(order_id: str):
    """
    Retrive an order by its ID
    :param order_id: Order ID as a string.
    :return: order object with string fields.
    """
    order = await MongoOrder.get(PydanticObjectId(order_id))
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    # Convert MongoDB ObjectId fields to string
    order.id = str(order.id) if isinstance(order.id, ObjectId) else order.id
    order.user_id = str(order.user_id) if isinstance(order.user_id, ObjectId) else order.user_id

    return order


@router.get("/orders/user/{User_id}", response_model=List[OrderResponse])
async def get_order_by_user(user_id: str):
    """
    Retrieve all orders placed by a specific user
    :param user_id: The ID of th user as a string.
    :return: Alist of the orders placed by the user.
    """
    try:
        # Convert the user_id to a PydanticObjectId
        user_obj_id = PydanticObjectId(user_id)

        # fect all oders with the specified user ID
        orders = await MongoOrder.find({"user_id": user_obj_id}).to_list()

        # check if oders were found
        if not orders:
            raise HTTPException(status_code=404, detail="No orders found for the specified user.")

        # convert each of the order's id to string for JSON serialization
        for order in orders:
            order.id = str(order.id)
            order.user_id = str(order.user_id)

        return orders
    except Exception as e:
        print(f"Error fecting oders for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail="An error occurred while retrieving user orders.")


@router.post("/create_dummy_user", response_model=dict)
async def create_dummy_user():
    dummy_user = MongoUser(
        username="dummy_user",
        email="dummy@example.com",
        hashed_password="hashed_test_pwd",
        balance=1000.0,  # Adjust balance as needed
        is_active=True
    )
    await dummy_user.insert()
    return {"message": "Dummy user created successfully", "user_id": str(dummy_user.id)}


@router.get("/users/orders", response_model=List[Dict])
async def get_users_with_orders(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    sort_by: Optional[str] = Query(None),
    sort_order: Optional[str] = Query("asc"),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    order_status: Optional[str] = Query(None),
    min_balance: Optional[float] = Query(None),
    max_balance: Optional[float] = Query(None)
):
    """
    Fetch users with their orders, with support for pagination, sorting, and filtering.
    """
    skip = (page - 1) * limit
    sort_order = 1 if sort_order == "asc" else -1
    sort_criteria = {sort_by: sort_order} if sort_by else None

    query_filters = {}
    if status:
        query_filters["status"] = status
    if search:
        query_filters["$or"] = [{"username": {"$regex": search, "$options": "i"}}, {"email": {"$regex": search, "$options": "i"}}]
    if min_balance is not None:
        query_filters["balance"] = {"$gte": min_balance}
    if max_balance is not None:
        query_filters["balance"] = {"$lte": max_balance, **query_filters.get("balance", {})}

    find_query = MongoUser.find(query_filters).skip(skip).limit(limit)
    if sort_criteria:
        find_query = find_query.sort(sort_criteria)

    users_with_orders = []
    async for user in find_query:
        order_query = MongoOrder.find({"user_id": user.id})
        if start_date:
            order_query = order_query.find({"start_time": {"$gte": start_date}})
        if end_date:
            order_query = order_query.find({"start_time": {"$lte": end_date}})
        if order_status:
            order_query = order_query.find({"status": order_status})

        user_orders = await order_query.to_list()
        user_data = {
            "username": user.username,
            "email": user.email,
            "balance": user.balance,
            "orders": [
                {
                    "order_id": str(order.id),
                    "symbol": order.symbol,
                    "amount": order.amount,
                    "prediction": order.prediction,
                    "trade_time": order.trade_time,
                    "locked_price": order.locked_price,
                    "status": order.status
                }
                for order in user_orders
            ]
        }
        users_with_orders.append(user_data)

    return users_with_orders

@router.get("/users/orders/stats", response_model=Dict)
async def get_users_with_orders_stats(
    min_wins: Optional[int] = Query(None, description="Minimum number of wins"),
    max_wins: Optional[int] = Query(None, description="Maximum number of wins"),
    min_losses: Optional[int] = Query(None, description="Minimum number of losses"),
    max_losses: Optional[int] = Query(None, description="Maximum number of losses")
):
    """
    Fetch aggregated statistics about users and their orders with options to filter by the number of wins and losses.
    """
    users_with_orders = []
    total_users = 0
    total_orders = 0
    most_wins = {"username": None, "wins": 0}

    async for user in MongoUser.find_all():
        user_orders = await MongoOrder.find(MongoOrder.user_id == user.id).to_list()
        wins = sum(1 for order in user_orders if order.status == "win")
        losses = sum(1 for order in user_orders if order.status == "lose")

        # Apply filters for wins and losses
        if min_wins is not None and wins < min_wins:
            continue
        if max_wins is not None and wins > max_wins:
            continue
        if min_losses is not None and losses < min_losses:
            continue
        if max_losses is not None and losses > max_losses:
            continue

        total_users += 1
        total_orders += len(user_orders)

        # Update most wins
        if wins > most_wins["wins"]:
            most_wins = {"username": user.username, "wins": wins}

        user_data = {
            "username": user.username,
            "email": user.email,
            "orders": len(user_orders),
            "wins": wins,
            "losses": losses
        }
        users_with_orders.append(user_data)

    return {
        "total_users": total_users,
        "total_orders": total_orders,
        "users_details": users_with_orders,
        "user_with_most_wins": most_wins
    }



@router.get("/users/active", response_model=List[Dict])
async def get_active_users():
    """
    Fetch all active users who have pending or recent orders within the last hour.
    """
    active_users = []
    current_time = datetime.utcnow()

    async for user in MongoUser.find(MongoUser.is_active == True):
        # Find all pending orders or recent orders placed in the last hour
        recent_orders = await MongoOrder.find({
            "user_id": user.id,
            "$or": [
                {"status": "pending"},  # Orders that are still pending
                {"start_time": {"$gte": current_time - timedelta(hours=1)}}  # Orders placed in the last hour
            ]
        }).to_list()

        if recent_orders:
            active_users.append({
                "username": user.username,
                "email": user.email,
                "active_orders_count": len(recent_orders)
            })

    return active_users
