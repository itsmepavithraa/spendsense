"""Generate ~5k realistic synthetic transactions for a demo user.

Run:  docker compose exec api python -m scripts.seed
"""
import csv
import random
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from sqlalchemy import delete, select

from app.database import SessionLocal
from app.models import Transaction, User
from app.security import hash_password

DEMO_EMAIL = "demo@spendsense.com"
DEMO_PASSWORD = "demo12345"
N_TRANSACTIONS = 4900          # + recurring subscriptions ~ 5k total
ANOMALY_RATE = 0.02
DAYS = 365

# category -> (merchants, min_amount, max_amount, sampling weight)
CATEGORIES = {
    "Food & Dining": (["Swiggy", "Zomato", "Domino's", "Starbucks", "McDonald's", "Cafe Coffee Day"], 150, 900, 25),
    "Groceries": (["BigBasket", "Blinkit", "DMart", "Reliance Fresh", "Zepto"], 200, 3000, 20),
    "Transport": (["Uber", "Ola", "Rapido", "Indian Railways", "Shell Petrol"], 60, 1500, 15),
    "Shopping": (["Amazon", "Flipkart", "Myntra", "Ajio", "Decathlon"], 300, 6000, 12),
    "Entertainment": (["BookMyShow", "PVR Cinemas", "Steam", "Inox"], 200, 1500, 8),
    "Utilities": (["Airtel", "Jio", "BESCOM Electricity", "Tata Power", "Indane Gas"], 300, 2500, 8),
    "Health": (["Apollo Pharmacy", "PharmEasy", "1mg", "Cult.fit"], 100, 2500, 7),
    "Education": (["Udemy", "Coursera", "Amazon Books"], 300, 3500, 5),
}

# monthly recurring subscriptions: (merchant, amount, day of month)
SUBSCRIPTIONS = [
    ("Netflix", 649, 5),
    ("Spotify", 119, 8),
    ("YouTube Premium", 129, 12),
    ("iCloud", 75, 15),
    ("Cult.fit Membership", 1500, 1),
    ("Hotstar", 299, 20),
]


def money(x: float) -> Decimal:
    return Decimal(str(round(x, 2)))


def random_datetime(now: datetime) -> datetime:
    day = now - timedelta(days=random.randint(0, DAYS - 1))
    # people spend more during the day than at 3 AM
    hour = random.choices(range(24), weights=[1] * 7 + [4] * 4 + [8] * 6 + [10] * 5 + [3] * 2)[0]
    when = day.replace(hour=hour, minute=random.randint(0, 59), second=random.randint(0, 59), microsecond=0)
    # for "today", a random hour can land in the future; never generate those
    return min(when, now)


def build_rows(user_id: int) -> list[dict]:
    now = datetime.now(timezone.utc)
    names = list(CATEGORIES)
    weights = [CATEGORIES[c][3] for c in names]
    rows = []

    # 1) everyday spending
    for _ in range(N_TRANSACTIONS):
        category = random.choices(names, weights=weights)[0]
        merchants, lo, hi, _ = CATEGORIES[category]
        # lognormal-ish: most purchases small, a few large
        amount = min(hi, max(lo, random.lognormvariate(0, 0.5) * (lo + hi) / 3))
        is_anomaly = random.random() < ANOMALY_RATE
        if is_anomaly:
            amount = hi * random.uniform(4, 10)       # unusually large purchase
        rows.append({
            "user_id": user_id,
            "amount": money(amount),
            "merchant": random.choice(merchants),
            "category": category,
            "is_anomaly": is_anomaly,
            "occurred_at": random_datetime(now),
        })

    # 2) recurring subscriptions (same amount, same day, every month)
    for merchant, amount, day in SUBSCRIPTIONS:
        for months_ago in range(12):
            month_start = (now.replace(day=1) - timedelta(days=30 * months_ago)).replace(day=1)
            when = month_start.replace(day=day, hour=6, minute=0, second=0, microsecond=0)
            if when <= now:
                rows.append({
                    "user_id": user_id,
                    "amount": money(amount),
                    "merchant": merchant,
                    "category": "Subscriptions",
                    "is_anomaly": False,
                    "occurred_at": when,
                })
    return rows


def main() -> None:
    random.seed(42)  # reproducible dataset
    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.email == DEMO_EMAIL))
        if user is None:
            user = User(
                email=DEMO_EMAIL,
                full_name="Demo User",
                hashed_password=hash_password(DEMO_PASSWORD),
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        else:  # re-running replaces old demo data
            db.execute(delete(Transaction).where(Transaction.user_id == user.id))
            db.commit()

        rows = build_rows(user.id)
        db.add_all(Transaction(**r) for r in rows)
        db.commit()

        out = Path("data")
        out.mkdir(exist_ok=True)
        with open(out / "transactions_seed.csv", "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["merchant", "amount", "category", "is_anomaly", "occurred_at"])
            writer.writeheader()
            for r in rows:
                writer.writerow({k: r[k] for k in writer.fieldnames})

        print(f"Seeded {len(rows)} transactions for {DEMO_EMAIL} (password: {DEMO_PASSWORD})")
    finally:
        db.close()


if __name__ == "__main__":
    main()
