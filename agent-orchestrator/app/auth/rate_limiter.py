"""In-memory rate limiter for login (and other endpoints).

Dono: auth-backend (FASE 3). Spec 14.1:
- Login: 5 requests/min per IP (V1 single-user, in-memory).
- 429 response with envelope: error=rate_limited, code=rate_limited,
  details={retryAfter: int}.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict


class RateLimiter:
    """In-memory sliding-window rate limiter.

    Thread-safe. Tracks request timestamps per key.
    """

    def __init__(self, max_requests: int, window_seconds: int) -> None:
        self._max_requests = max_requests
        self._window = window_seconds
        self._lock = threading.Lock()
        self._requests: dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, key: str) -> tuple[bool, int]:
        """Check if a request is allowed for the given key.

        Returns:
            (allowed, retry_after_seconds). If not allowed, retry_after is
            the number of seconds until the oldest request in the window expires.
        """
        with self._lock:
            now = time.time()
            window_start = now - self._window
            # Remove expired entries.
            self._requests[key] = [t for t in self._requests[key] if t > window_start]
            if len(self._requests[key]) < self._max_requests:
                self._requests[key].append(now)
                return True, 0
            # Not allowed: compute retry_after from oldest entry in window.
            oldest = self._requests[key][0]
            retry_after = max(1, int(self._window - (now - oldest)))
            return False, retry_after

    def cleanup(self) -> None:
        """Remove all entries (for testing)."""
        with self._lock:
            self._requests.clear()


# Login rate limiter: 5 requests per minute per IP.
login_rate_limiter = RateLimiter(max_requests=5, window_seconds=60)
