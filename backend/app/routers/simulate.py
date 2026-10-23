"""Fake "bank feed" for demos: POST /simulate/start streams a random transaction
every few seconds, so the live dashboard always has something to show.

Each simulated transaction goes through the exact same path as a real one:
saved to the DB, categorized and scored by the ML models, then pushed over
the WebSocket.
"""
import asyncio
import logging
import random
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from starlette.concurrency import run_in_threadpool

from app.database import SessionLocal
from app.deps import get_current_user
from app.models import User
from app.realtime import manager, transaction_events
from app.services import create_transaction_for_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/simulate", tags=["simulate"])

# merchant -> (typical min amount, typical max amount)
MERCHANTS = {
    "Swiggy": (150, 900),
    "Zomato": (150, 900),
    "BigBasket": (200, 3000),
    "Uber": (60, 1500),
    "Amazon": (300, 6000),
    "Myntra": (300, 6000),
    "BookMyShow": (200, 1500),
    "Airtel": (300, 2500),
    "Apollo Pharmacy": (100, 2500),
    "Netflix": (649, 649),
}
ANOMALY_CHANCE = 0.08  # 8% of simulated transactions are unusually large

# user_id -> the background task generating that user's fake transactions
_tasks: dict[int, asyncio.Task] = {}


def _make_one(user_id: int) -> list[dict]:
    """Create one random transaction (sync, DB work) and return its events."""
    merchant, (lo, hi) = random.choice(list(MERCHANTS.items()))
    amount = random.uniform(lo, hi)
    if random.random() < ANOMALY_CHANCE:
        amount = hi * random.uniform(4, 10)
    with SessionLocal() as db:
        txn = create_transaction_for_user(
            db, user_id, merchant, Decimal(str(round(amount, 2)))
        )
        return transaction_events(txn)


async def _run(user_id: int, interval: float) -> None:
    while True:
        try:
            events = await run_in_threadpool(_make_one, user_id)
            await manager.send_events(user_id, events)
        except Exception:  # keep the feed alive if one iteration fails
            logger.exception("simulator iteration failed")
        await asyncio.sleep(interval)


@router.post("/start")
async def start(
    interval: float = Query(3.0, ge=0.5, le=60, description="seconds between transactions"),
    user: User = Depends(get_current_user),
):
    task = _tasks.get(user.id)
    if task and not task.done():
        return {"status": "already running"}
    _tasks[user.id] = asyncio.create_task(_run(user.id, interval))
    return {"status": "started", "interval_seconds": interval}


@router.post("/stop")
async def stop(user: User = Depends(get_current_user)):
    task = _tasks.pop(user.id, None)
    if task and not task.done():
        task.cancel()
        return {"status": "stopped"}
    return {"status": "not running"}
