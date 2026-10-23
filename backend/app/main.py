"""SpendSense API entry point: creates the FastAPI app and registers routers.

Run locally with:  uvicorn app.main:app --reload
Interactive docs (Swagger UI) are served at /docs.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import auth, simulate, transactions, ws

app = FastAPI(title="SpendSense API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # the Next.js dev server (Day 3)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(transactions.router)
app.include_router(ws.router)
app.include_router(simulate.router)


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}
