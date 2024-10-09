# trading_platform_backend/celery_worker.py


from celery import Celery
import asyncio
from app.services.trading_service import evaluate_order_outcome_mongo

app = Celery('tasks', broker='redis://localhost:6379/0')

@app.task
def evaluate_order_task(order_id):
    from app.services.trading_service import evaluate_order_outcome_mongo
    asyncio.run(evaluate_order_outcome_mongo(order_id))
