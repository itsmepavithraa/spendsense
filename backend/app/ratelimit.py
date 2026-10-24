"""Abuse protection for a public site: rate limits and a login lockout.

Why it matters: sign-up and login are open to the whole internet. Without limits one
person (or bot) can create thousands of accounts, hammer the CPU-heavy statement import,
or try passwords endlessly against someone's email address.

How it works: a sliding window per key (the visitor's address, or an email). Everything is
kept in this process's memory, which is correct for the single API instance this project
runs; with several instances it would move to Redis. A restart clears the counters, which is
acceptable for abuse protection.
"""
import time
from collections import defaultdict, deque
from typing import Callable

from fastapi import Depends, HTTPException, Request, status

from app.config import settings


class SlidingWindow:
    """Allows at most `limit` hits per `window` seconds for each key."""

    SWEEP_EVERY = 128  # operations between clean-ups of keys that have gone quiet

    def __init__(self, limit: int, window: float, clock: Callable[[], float] = time.monotonic):
        self.limit, self.window, self.clock = limit, window, clock
        self._hits: dict[str, deque] = defaultdict(deque)
        self._operations = 0

    def _sweep(self) -> None:
        """Drop every key whose latest hit is outside the window. Without this a bot that uses a
        new address each time would leave one entry behind per address, forever."""
        self._operations += 1
        if self._operations % self.SWEEP_EVERY:
            return
        cutoff = self.clock() - self.window
        for key in [k for k, hits in self._hits.items() if not hits or hits[-1] <= cutoff]:
            del self._hits[key]

    def _trim(self, key: str) -> deque:
        self._sweep()
        hits, now = self._hits[key], self.clock()
        while hits and hits[0] <= now - self.window:
            hits.popleft()
        if not hits:
            self._hits.pop(key, None)  # forget idle keys so memory can't grow without bound
            return deque()
        return hits

    def allow(self, key: str) -> bool:
        """Record a hit and say whether it is within the limit."""
        hits = self._trim(key)
        if len(hits) >= self.limit:
            return False
        self._hits[key] = hits
        hits.append(self.clock())
        return True

    def blocked(self, key: str) -> bool:
        """Is this key over the limit right now? (Does not record a hit.)"""
        return len(self._trim(key)) >= self.limit

    def record(self, key: str) -> None:
        hits = self._trim(key)
        self._hits[key] = hits
        hits.append(self.clock())

    def reset(self, key: str | None = None) -> None:
        if key is None:
            self._hits.clear()
        else:
            self._hits.pop(key, None)

    def retry_after(self, key: str) -> int:
        hits = self._trim(key)
        return max(1, int(hits[0] + self.window - self.clock()) + 1) if hits else 1


def client_address(request: Request) -> str:
    """The visitor's address. Only trusts X-Forwarded-For when the hosting proxy is known to set it."""
    if settings.trust_proxy:
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[0].strip()  # the first entry is the original visitor
    return request.client.host if request.client else "unknown"


def too_many(retry_after: int) -> HTTPException:
    return HTTPException(
        status.HTTP_429_TOO_MANY_REQUESTS,
        "Too many attempts. Please wait a little and try again.",
        headers={"Retry-After": str(retry_after)},
    )


def limit_by_address(name: str, limit: int, window: float) -> Callable:
    """A FastAPI dependency: at most `limit` calls per `window` seconds per visitor address."""
    window_counter = SlidingWindow(limit, window)
    ALL_LIMITERS.append(window_counter)

    def dependency(request: Request) -> None:
        if not settings.rate_limit_enabled:
            return
        address = client_address(request)
        if not window_counter.allow(f"{name}:{address}"):
            raise too_many(window_counter.retry_after(f"{name}:{address}"))

    return Depends(dependency)


# every limiter registers here so tests can reset them all at once
ALL_LIMITERS: list[SlidingWindow] = []

# Failed logins per email, regardless of where they come from: stops a password-guessing
# attack that rotates through many addresses. A successful login clears the count.
FAILED_LOGINS = SlidingWindow(limit=5, window=15 * 60)
ALL_LIMITERS.append(FAILED_LOGINS)


def reset_all() -> None:
    for limiter in ALL_LIMITERS:
        limiter.reset()
