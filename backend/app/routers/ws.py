"""WebSocket endpoint: ws://host/ws?token=<JWT>

Browsers can't set an Authorization header on a WebSocket, so the JWT is sent
as a query parameter and verified before the connection is accepted.
"""
import jwt
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from starlette.concurrency import run_in_threadpool

from app.database import SessionLocal
from app.models import User
from app.realtime import manager
from app.security import decode_access_token

router = APIRouter(tags=["realtime"])


def _authenticate(token: str) -> int | None:
    """Return the user id for a valid token of an existing user, else None."""
    try:
        user_id = decode_access_token(token)
    except (jwt.PyJWTError, KeyError, ValueError):
        return None
    with SessionLocal() as db:
        return user_id if db.get(User, user_id) else None


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str = Query(...)):
    # DB lookup is blocking, so run it off the event loop
    user_id = await run_in_threadpool(_authenticate, token)
    if user_id is None:
        await websocket.close(code=1008)  # 1008 = policy violation (unauthenticated)
        return

    await manager.connect(user_id, websocket)
    await websocket.send_json({"type": "connected", "data": {"user_id": user_id}})
    try:
        # We only push to clients; reading keeps the socket open and
        # lets us notice when the browser tab closes.
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(user_id, websocket)
