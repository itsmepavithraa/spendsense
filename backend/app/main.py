"""SpendSense API entry point: creates the FastAPI app and registers routers.

Run locally with:  uvicorn app.main:app --reload
Interactive docs (Swagger UI) are served at /docs.
"""
import logging
import re

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select
from starlette.requests import Request

from app.config import settings
from app.database import SessionLocal
from app.models import User
from app.routers import analytics, auth, billing, merchants, simulate, transactions, ws


class RedactTokens(logging.Filter):
    """The real-time connection puts the login token in the URL (/ws?token=...), and the
    web server logs every URL. Blank it out so tokens never end up in log files."""

    PATTERN = re.compile(r"(token=)[^\s&\"']+")

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = self.PATTERN.sub(r"\1REDACTED", str(record.msg))
        if record.args:
            record.args = tuple(self.PATTERN.sub(r"\1REDACTED", a) if isinstance(a, str) else a for a in record.args)
        return True


for _name in ("uvicorn.access", "uvicorn.error", "uvicorn"):
    logging.getLogger(_name).addFilter(RedactTokens())

app = FastAPI(title="SpendSense API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,  # set CORS_ORIGINS in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    """Standard browser protections on every response."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"  # don't guess file types
    response.headers["X-Frame-Options"] = "DENY"  # the API is never shown inside someone else's page
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Strict-Transport-Security"] = "max-age=31536000"  # browsers insist on HTTPS
    return response


app.include_router(auth.router)
app.include_router(transactions.router)
app.include_router(analytics.router)
app.include_router(billing.router)
app.include_router(merchants.router)
app.include_router(ws.router)
app.include_router(simulate.router)


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}


@app.get("/config", tags=["meta"])
def public_config():
    """What the website needs to know to show the right screens. Nothing secret."""
    with SessionLocal() as db:
        full = bool(settings.max_users) and db.scalar(select(func.count(User.id))) >= settings.max_users
    return {
        "registration_open": settings.allow_registration and not full,
        "payments_enabled": settings.payments_enabled,
        "demo_email": settings.demo_email,
        "max_transactions_per_user": settings.max_transactions_per_user,
    }
