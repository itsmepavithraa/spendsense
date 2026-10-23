"""Real-time layer: tracks each user's open WebSockets and pushes events to them.

Flow:  a transaction is created (REST call or simulator)
       -> events are built (transaction.created, plus anomaly.alert if flagged)
       -> manager.send_events() pushes them to every open tab of that user.

Each user only ever receives their own events: connections are stored per user id.

Note: this manager lives in one server process's memory. To run several API
servers behind a load balancer, events would be published through Redis
pub/sub (planned) so every server can reach every user's sockets.
"""
from collections import defaultdict

from fastapi import WebSocket

from app.models import Transaction
from app.schemas import TransactionOut


class ConnectionManager:
    def __init__(self) -> None:
        # user_id -> the set of that user's open sockets (one per browser tab)
        self._connections: dict[int, set[WebSocket]] = defaultdict(set)

    async def connect(self, user_id: int, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections[user_id].add(websocket)

    def disconnect(self, user_id: int, websocket: WebSocket) -> None:
        self._connections[user_id].discard(websocket)
        if not self._connections[user_id]:
            del self._connections[user_id]

    async def send_events(self, user_id: int, events: list[dict]) -> None:
        """Push events to all of one user's sockets; drop sockets that died."""
        for websocket in list(self._connections.get(user_id, ())):
            try:
                for event in events:
                    await websocket.send_json(event)
            except Exception:
                self.disconnect(user_id, websocket)


manager = ConnectionManager()


def transaction_events(txn: Transaction) -> list[dict]:
    """Turn a saved transaction into the JSON events the frontend listens for.

    Built as plain dicts *before* the DB session closes, so nothing later
    needs to touch the ORM object.
    """
    data = TransactionOut.model_validate(txn).model_dump(mode="json")
    events = [{"type": "transaction.created", "data": data}]
    if txn.is_anomaly:
        events.append(
            {
                "type": "anomaly.alert",
                "data": {
                    **data,
                    "message": f"Unusual {txn.category} charge at {txn.merchant}: {txn.amount}",
                },
            }
        )
    return events
