# trading_platform_backend/app/routes/currencies.py

# Routes for handling currencies

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import TradingPair
from app.schemas import TradingPairResponse, TradingPairCreate
from app.utils import fetch_real_time_prices, update_or_create_trading_pair

router = APIRouter()

@router.get("/trading_pairs", response_model=list[TradingPairResponse])
def get_all_trading_pairs(db: Session = Depends(get_db)):
    """
    Get all trading pairs with their current prices.
    """
    trading_pairs = db.query(TradingPair).all()
    if not trading_pairs:
        raise HTTPException(status_code=404, detail="No trading pairs found.")
    return trading_pairs


@router.post("/trading_pairs", response_model=TradingPairResponse)
def create_or_update_trading_pair(pair: TradingPairCreate, db: Session = Depends(get_db)):
    """
    Create a new trading pair or update an existing one manually (admin functionality).
    """
    symbol = pair.symbol.upper()
    price = pair.price

    trading_pair = db.query(TradingPair).filter(TradingPair.symbol == symbol).first()

    if trading_pair:
        trading_pair.price = price
        db.commit()
        db.refresh(trading_pair)
        return trading_pair
    else:
        trading_pair = TradingPair(symbol=symbol, price=price)
        db.add(trading_pair)
        db.commit()
        db.refresh(trading_pair)
        return trading_pair


@router.post("/update_prices")
def update_prices(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """
    Trigger a background task to update the prices of all trading pairs (manual trigger).
    """
    background_tasks.add_task(fetch_real_time_prices, db)
    return {"message": "Price update initiated in the background."}
