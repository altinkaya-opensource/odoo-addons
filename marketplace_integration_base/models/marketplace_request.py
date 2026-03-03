# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import time
from collections import deque
from threading import Lock


class MarketplaceRateLimiter:
    """Configurable sliding-window rate limiter.

    Uses a deque to track request timestamps within a time window.
    Thread-safe via a threading lock.
    """

    def __init__(self, max_requests=50, time_window=10):
        self.max_requests = max_requests
        self.time_window = time_window
        self.requests = deque()
        self.lock = Lock()

    def acquire(self):
        """Wait until a request can be made within rate limits."""
        with self.lock:
            now = time.time()
            # Remove old requests outside the time window
            while self.requests and self.requests[0] < now - self.time_window:
                self.requests.popleft()

            if len(self.requests) >= self.max_requests:
                # Wait until oldest request expires
                sleep_time = self.requests[0] + self.time_window - now
                if sleep_time > 0:
                    time.sleep(sleep_time)
                # Clean up again after sleeping
                now = time.time()
                while self.requests and self.requests[0] < now - self.time_window:
                    self.requests.popleft()

            self.requests.append(time.time())


class MarketplaceAPIError(Exception):
    """Base exception for marketplace API errors."""

    def __init__(self, message, status_code=None, response_data=None):
        super().__init__(message)
        self.status_code = status_code
        self.response_data = response_data
