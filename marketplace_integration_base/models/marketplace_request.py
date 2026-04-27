# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import base64
import json
import logging
import time
from collections import deque
from threading import Lock

import requests

_logger = logging.getLogger(__name__)


class MarketplaceRateLimiter:
    """Thread-safe sliding-window rate limiter for marketplace APIs."""

    def __init__(self, max_requests=100, time_window=1):
        self.max_requests = max_requests
        self.time_window = time_window
        self.requests = deque()
        self.lock = Lock()

    def acquire(self):
        """Wait until a request can be made within the configured rate limit."""
        with self.lock:
            now = time.time()
            while self.requests and self.requests[0] < now - self.time_window:
                self.requests.popleft()

            if len(self.requests) >= self.max_requests:
                sleep_time = self.requests[0] + self.time_window - now
                if sleep_time > 0:
                    time.sleep(sleep_time)
                now = time.time()
                while self.requests and self.requests[0] < now - self.time_window:
                    self.requests.popleft()

            self.requests.append(time.time())


class MarketplaceAPIError(Exception):
    """Exception raised for marketplace API errors."""

    def __init__(self, message, status_code=None, response_data=None):
        super().__init__(message)
        self.status_code = status_code
        self.response_data = response_data


class MarketplaceRequest:
    """Shared HTTP behavior for marketplace API clients."""

    api_name = "Marketplace"
    success_status_codes = (200, 201)
    error_class = MarketplaceAPIError

    def _build_basic_auth_header(self, username, password):
        auth_string = f"{username}:{password}"
        auth_bytes = auth_string.encode("utf-8")
        auth_b64 = base64.b64encode(auth_bytes).decode("utf-8")
        return f"Basic {auth_b64}"

    def _extract_error_message(self, error_data, fallback):
        error_msg = error_data.get("message", fallback)
        if "errors" in error_data:
            errors = error_data["errors"]
            if isinstance(errors, list):
                error_msg = "; ".join(
                    error.get("message", str(error))
                    if isinstance(error, dict)
                    else str(error)
                    for error in errors
                )
        return error_msg

    def _request_json(
        self,
        method,
        url,
        headers,
        params=None,
        json_data=None,
        timeout=60,
        skip_rate_limit=False,
    ):
        if not skip_rate_limit and getattr(self, "rate_limiter", False):
            self.rate_limiter.acquire()

        _logger.debug(
            "%s API %s %s - params: %s, body: %s",
            self.api_name,
            method,
            url,
            params,
            json_data,
        )

        try:
            response = requests.request(
                method=method,
                url=url,
                headers=headers,
                params=params,
                json=json_data,
                timeout=timeout,
            )
        except requests.RequestException as e:
            raise self.error_class(f"Request failed: {str(e)}") from e

        _logger.debug(
            "%s API response: %s - %s",
            self.api_name,
            response.status_code,
            response.text[:500] if response.text else "",
        )

        if response.status_code in self.success_status_codes:
            try:
                return response.json() if response.text else {}
            except json.JSONDecodeError:
                return {"raw": response.text}

        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After", "1")
            raise self.error_class(
                f"Rate limit exceeded. Retry after {retry_after}s",
                status_code=429,
            )

        try:
            error_data = response.json()
            error_msg = self._extract_error_message(error_data, response.text)
        except json.JSONDecodeError:
            error_data = None
            error_msg = response.text

        raise self.error_class(
            f"API error ({response.status_code}): {error_msg}",
            status_code=response.status_code,
            response_data=error_data,
        )
