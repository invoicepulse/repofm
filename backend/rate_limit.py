"""
RepoFM — In-memory IP-based rate limiter.

Tracks POST /analyze requests per client IP using a sliding window.
State is not persisted — resets on process restart.
"""

import time
from datetime import datetime, timezone

from fastapi import HTTPException


class RateLimitExceeded(HTTPException):
    """Custom exception carrying the ``reset_at`` ISO timestamp."""

    def __init__(self, detail: str, reset_at: str) -> None:
        super().__init__(status_code=429, detail=detail)
        self.reset_at = reset_at


class RateLimiter:
    """Sliding-window rate limiter backed by an in-memory dict."""

    def __init__(self, max_requests: int = 2, window_seconds: int = 3600) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[str, list[float]] = {}

    def _prune(self, ip: str) -> None:
        """Remove timestamps older than the sliding window for the given IP."""
        cutoff = time.time() - self.window_seconds
        if ip in self._requests:
            self._requests[ip] = [
                ts for ts in self._requests[ip] if ts > cutoff
            ]

    def check(self, ip: str) -> None:
        """Raise ``RateLimitExceeded`` (HTTP 429) if the IP has reached the request limit.

        The 429 response body includes both ``detail`` and ``reset_at`` fields.
        ``reset_at`` is an ISO 8601 UTC timestamp indicating when the oldest
        request in the window expires.
        """
        self._prune(ip)
        timestamps = self._requests.get(ip, [])
        if len(timestamps) >= self.max_requests:
            # The earliest request in the window determines when the limit resets
            earliest = min(timestamps)
            reset_epoch = earliest + self.window_seconds
            reset_at = datetime.fromtimestamp(reset_epoch, tz=timezone.utc).isoformat()
            raise RateLimitExceeded(
                detail=f"Rate limit exceeded. Resets at {reset_at}.",
                reset_at=reset_at,
            )

    def record(self, ip: str) -> None:
        """Record a request for *ip* and prune stale entries."""
        now = time.time()
        if ip not in self._requests:
            self._requests[ip] = []
        self._requests[ip].append(now)
        self._prune(ip)
