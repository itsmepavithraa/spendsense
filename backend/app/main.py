"""SpendSense API entry point: creates the FastAPI app and registers routers.

Run locally with:  uvicorn app.main:app --reload
Interactive docs (Swagger UI) are served at /docs.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import analytics, auth, billing, simulate, transactions, ws

app = FastAPI(title="SpendSense API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,  # set CORS_ORIGINS in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(transactions.router)
app.include_router(analytics.router)
app.include_router(billing.router)
app.include_router(ws.router)
app.include_router(simulate.router)


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}
