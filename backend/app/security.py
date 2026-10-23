"""Password hashing (bcrypt) and JWT access tokens.

We never store passwords: bcrypt is a slow one-way hash with a random salt.
After login the client gets a signed JWT carrying the user id ("sub") and an
expiry ("exp"); only someone holding SECRET_KEY can forge one.
"""
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.config import settings


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def decode_access_token(token: str) -> int:
    """Return the user id inside a valid JWT.

    Raises jwt.PyJWTError (bad signature / expired) or ValueError / KeyError
    (malformed payload). Shared by the HTTP auth dependency and the WebSocket.
    """
    payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    return int(payload["sub"])


def create_access_token(user_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.access_token_expire_minutes
    )
    payload = {"sub": str(user_id), "exp": expire}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)
