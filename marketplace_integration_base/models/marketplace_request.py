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
    """Configurable rate limiter using sliding window algorithm.

    Thread-safe. Uses a deque to track request timestamps within
    the configured time window.

    Args:
        max_requests: Maximum number of requests allowed per time window
        time_window: Time window in seconds
    """

    def __init__(self, max_requests=100, time_window=1):
        self.max_requests = max_requests
        self.time_window = time_window
        self.requests = deque()
        self.lock = Lock()

    def acquire(self):
        """Wait until a request can be made within rate limits."""
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
    """Base exception for marketplace API errors.

    Attributes:
        status_code: HTTP status code from the API response
        response_data: Parsed JSON error data from the API response
    """

    def __init__(self, message, status_code=None, response_data=None):
        super().__init__(message)
        self.status_code = status_code
        self.response_data = response_data


class MarketplaceRequest:
    """Base API client for marketplace integrations.

    Provides common functionality: Basic Auth, rate limiting,
    request execution, response parsing, and error handling.

    Subclasses should:
    - Call super().__init__() with credentials and rate limiter
    - Define their own _make_request() with marketplace-specific URL building
    - Implement test_connection()
    """

    def __init__(self, username, password, user_agent="", rate_limiter=None):
        """Initialize base API client.

        Args:
            username: API username (or api_key)
            password: API password (or api_secret)
            user_agent: User-Agent header value
            rate_limiter: MarketplaceRateLimiter instance
        """
        self.user_agent = user_agent
        self.rate_limiter = rate_limiter or MarketplaceRateLimiter()

        # Build Basic Auth header
        auth_string = f"{username}:{password}"
        auth_b64 = base64.b64encode(auth_string.encode("utf-8")).decode("utf-8")
        self.auth_header = f"Basic {auth_b64}"

    def _get_headers(self):
        """Get common headers for API requests."""
        return {
            "Authorization": self.auth_header,
            "User-Agent": self.user_agent,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _send_request(
        self,
        method,
        url,
        params=None,
        json_data=None,
        timeout=60,
        extra_headers=None,
        skip_rate_limit=False,
    ):
        """Execute an API request with rate limiting and error handling.

        This is the low-level method that concrete _make_request() methods
        should delegate to after building the full URL.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            url: Full URL to request
            params: Query parameters
            json_data: JSON body data
            timeout: Request timeout in seconds
            extra_headers: Additional headers to merge
            skip_rate_limit: Skip rate limiting for this request

        Returns:
            Response JSON data

        Raises:
            MarketplaceAPIError: If the API returns an error
        """
        if not skip_rate_limit and self.rate_limiter:
            self.rate_limiter.acquire()

        headers = self._get_headers()
        if extra_headers:
            headers.update(extra_headers)

        _logger.debug(
            "Marketplace API %s %s - params: %s, body: %s",
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
            raise MarketplaceAPIError(f"Request failed: {str(e)}") from e

        log_level = (
            logging.DEBUG
            if response.status_code in (200, 201, 204)
            else logging.WARNING
        )
        _logger.log(
            log_level,
            "Marketplace API response: %s %s - %s",
            method,
            url,
            response.text[:1000] if response.text else "",
        )

        if response.status_code in (200, 201, 204):
            try:
                return response.json() if response.text else {}
            except json.JSONDecodeError:
                return {"raw": response.text}

        # Handle rate limiting
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After", "1")
            raise MarketplaceAPIError(
                f"Rate limit exceeded. Retry after {retry_after}s",
                status_code=429,
            )

        # Parse and raise error
        error_msg, error_data = self._parse_error_response(response)
        raise MarketplaceAPIError(
            f"API error ({response.status_code}): {error_msg}",
            status_code=response.status_code,
            response_data=error_data,
        )

    @staticmethod
    def _parse_error_response(response):
        """Parse error message and data from an HTTP error response.

        Returns:
            Tuple of (error_message, error_data)
        """
        try:
            error_data = response.json()
            error_msg = error_data.get("message", response.text)
            if "errors" in error_data:
                error_msgs = error_data["errors"]
                if isinstance(error_msgs, list):
                    error_msg = "; ".join(str(e) for e in error_msgs)
        except json.JSONDecodeError:
            error_data = None
            error_msg = response.text
        return error_msg, error_data

    def test_connection(self):
        """Test API connection. Must be overridden by subclass."""
        raise NotImplementedError
