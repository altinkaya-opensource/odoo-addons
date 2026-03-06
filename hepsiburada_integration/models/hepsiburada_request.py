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

# Hepsiburada has separate service URLs for each domain
HEPSIBURADA_SERVICE_URLS = {
    "stage": {
        "oms": "https://oms-external-sit.hepsiburada.com",
        "shipping": "https://shipping-external-sit.hepsiburada.com",
        "finance": "https://mpfinance-external-sit.hepsiburada.com",
        "asktoseller": "https://api-asktoseller-merchant-sit.hepsiburada.com",
    },
    "prod": {
        "oms": "https://oms-external.hepsiburada.com",
        "shipping": "https://shipping-external.hepsiburada.com",
        "finance": "https://mpfinance-external.hepsiburada.com",
        "asktoseller": "https://api-asktoseller-merchant.hepsiburada.com",
    },
}


class HepsiburadaRateLimiter:
    """Rate limiter for Hepsiburada API (100 requests per second)."""

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


class HepsiburadaAPIError(Exception):
    """Exception raised for Hepsiburada API errors."""

    def __init__(self, message, status_code=None, response_data=None):
        super().__init__(message)
        self.status_code = status_code
        self.response_data = response_data


class HepsiburadaRequest:
    """API client for Hepsiburada marketplace integration.

    Handles authentication, rate limiting, and all API communication.
    Only implements OMS and Shipping endpoints needed for order import,
    invoice sending, and status updates.
    """

    def __init__(
        self, merchant_id, username, password, environment="stage", user_agent=""
    ):
        """Initialize Hepsiburada API client.

        Args:
            merchant_id: Hepsiburada merchant ID
            username: API username
            password: API password
            environment: 'stage' for testing, 'prod' for production
            user_agent: User-Agent header value
        """
        self.merchant_id = merchant_id
        self.username = username
        self.password = password
        self.environment = environment
        self.user_agent = user_agent or merchant_id
        self.service_urls = HEPSIBURADA_SERVICE_URLS.get(
            environment, HEPSIBURADA_SERVICE_URLS["stage"]
        )
        self.rate_limiter = HepsiburadaRateLimiter()

        # Build auth header (Basic Auth)
        auth_string = f"{username}:{password}"
        auth_bytes = auth_string.encode("utf-8")
        auth_b64 = base64.b64encode(auth_bytes).decode("utf-8")
        self.auth_header = f"Basic {auth_b64}"

    def _get_headers(self):
        """Get common headers for API requests."""
        return {
            "Authorization": self.auth_header,
            "User-Agent": self.user_agent,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _make_request(self, method, service, endpoint, params=None, json_data=None):
        """Make an API request with rate limiting and error handling.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            service: Service name ('oms', 'shipping')
            endpoint: API endpoint path
            params: Query parameters
            json_data: JSON body data

        Returns:
            Response JSON data

        Raises:
            HepsiburadaAPIError: If the API returns an error
        """
        self.rate_limiter.acquire()

        base_url = self.service_urls.get(service)
        if not base_url:
            raise HepsiburadaAPIError(f"Unknown service: {service}")

        url = f"{base_url}{endpoint}"
        headers = self._get_headers()

        # AskToSeller API requires merchantId header on all requests
        if service == "asktoseller":
            headers["merchantId"] = self.merchant_id

        _logger.debug(
            "HB API %s %s - params: %s, body: %s",
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
                timeout=60,
            )
        except requests.RequestException as e:
            raise HepsiburadaAPIError(f"Request failed: {str(e)}") from e

        _logger.debug(
            "HB API response: %s - %s",
            response.status_code,
            response.text[:500] if response.text else "",
        )

        if response.status_code in (200, 201, 204):
            try:
                return response.json() if response.text else {}
            except json.JSONDecodeError:
                return {"raw": response.text}

        # Handle rate limiting
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After", "1")
            raise HepsiburadaAPIError(
                f"Rate limit exceeded. Retry after {retry_after}s",
                status_code=429,
            )

        # Handle errors
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

        raise HepsiburadaAPIError(
            f"API error ({response.status_code}): {error_msg}",
            status_code=response.status_code,
            response_data=error_data,
        )

    # ==================== Order Methods (OMS) ====================

    def get_paid_orders(self, offset=0, limit=50):
        """Get paid orders (ready to process).

        Args:
            offset: Pagination offset
            limit: Page size (max 50)

        Returns:
            List of order line item dicts
        """
        endpoint = f"/orders/merchantid/{self.merchant_id}"
        params = {"offset": offset, "limit": min(limit, 50)}
        return self._make_request("GET", "oms", endpoint, params=params)

    def get_packages(self, offset=0, limit=50):
        """Get packages with full order data.

        Args:
            offset: Pagination offset
            limit: Page size (max 50)

        Returns:
            List of package dicts with nested items
        """
        endpoint = f"/packages/merchantid/{self.merchant_id}"
        params = {"offset": offset, "limit": min(limit, 50)}
        return self._make_request("GET", "oms", endpoint, params=params)

    def get_shipped_packages(self, offset=0, limit=50):
        """Get shipped (in transit) packages."""
        endpoint = f"/packages/merchantid/{self.merchant_id}/shipped"
        params = {"offset": offset, "limit": min(limit, 50)}
        return self._make_request("GET", "oms", endpoint, params=params)

    def get_delivered_packages(self, offset=0, limit=50):
        """Get delivered packages."""
        endpoint = f"/packages/merchantid/{self.merchant_id}/delivered"
        params = {"offset": offset, "limit": min(limit, 50)}
        return self._make_request("GET", "oms", endpoint, params=params)

    def get_undelivered_packages(self, offset=0, limit=50):
        """Get undelivered packages."""
        endpoint = f"/packages/merchantid/{self.merchant_id}/undelivered"
        params = {"offset": offset, "limit": min(limit, 50)}
        return self._make_request("GET", "oms", endpoint, params=params)

    def get_cancelled_packages(self, offset=0, limit=50):
        """Get cancelled packages."""
        endpoint = f"/packages/merchantid/{self.merchant_id}/cancelled"
        params = {"offset": offset, "limit": min(limit, 50)}
        return self._make_request("GET", "oms", endpoint, params=params)

    def get_payment_awaiting_orders(self, offset=0, limit=50):
        """Get orders awaiting payment."""
        endpoint = f"/orders/merchantid/{self.merchant_id}/paymentawaiting"
        params = {"offset": offset, "limit": min(limit, 50)}
        return self._make_request("GET", "oms", endpoint, params=params)

    def get_order_detail(self, order_number):
        """Get detailed order by order number.

        Args:
            order_number: Hepsiburada order number

        Returns:
            Order detail dict with items
        """
        endpoint = f"/orders/merchantid/{self.merchant_id}/ordernumber/{order_number}"
        return self._make_request("GET", "oms", endpoint)

    # ==================== Package Methods (OMS) ====================

    def create_package(self, line_items):
        """Create a package for line items.

        Args:
            line_items: List of dicts with 'id' (lineItemId GUID)
                        and 'quantity'

        Returns:
            Package creation response
        """
        endpoint = f"/packages/merchantid/{self.merchant_id}"
        json_data = {
            "lineItemRequests": line_items,
        }
        return self._make_request("POST", "oms", endpoint, json_data=json_data)

    def get_package_detail(self, package_number):
        """Get package details by package number.

        Args:
            package_number: Package number

        Returns:
            Package detail dict
        """
        endpoint = (
            f"/packages/merchantid/{self.merchant_id}/packagenumber/{package_number}"
        )
        return self._make_request("GET", "oms", endpoint)

    def set_package_intransit(self, data):
        """Mark a package as in-transit (shipped).

        Args:
            data: Dict with packageNumber, shippedDate, trackingInfoCode

        Returns:
            Response data
        """
        package_number = data.get("packageNumber")
        endpoint = (
            f"/packages/merchantid/{self.merchant_id}"
            f"/packagenumber/{package_number}/intransit"
        )
        return self._make_request("POST", "oms", endpoint, json_data=data)

    def set_package_delivered(self, data):
        """Mark a package as delivered.

        Args:
            data: Dict with packageNumber, receivedDate, receivedBy

        Returns:
            Response data
        """
        package_number = data.get("packageNumber")
        endpoint = (
            f"/packages/merchantid/{self.merchant_id}"
            f"/packagenumber/{package_number}/deliver"
        )
        return self._make_request("POST", "oms", endpoint, json_data=data)

    def upload_invoice_link(self, package_number, invoice_url):
        """Upload invoice link for a package.

        Args:
            package_number: Package number
            invoice_url: Public URL to invoice

        Returns:
            Response data
        """
        endpoint = (
            f"/packages/merchantid/{self.merchant_id}"
            f"/packagenumber/{package_number}/invoice"
        )
        json_data = {"invoiceLink": invoice_url}
        return self._make_request("PUT", "oms", endpoint, json_data=json_data)

    def cancel_line_item(self, line_item_id):
        """Cancel a single line item.

        Args:
            line_item_id: Line item ID to cancel

        Returns:
            Response data
        """
        endpoint = (
            f"/lineitems/merchantid/{self.merchant_id}"
            f"/id/{line_item_id}/cancelbymerchant"
        )
        return self._make_request("POST", "oms", endpoint)

    # ==================== Shipping Methods ====================

    def get_cargo_firms(self):
        """Get available cargo firms for this merchant.

        Returns:
            List of cargo firm dicts
        """
        endpoint = f"/cargoFirms/{self.merchant_id}"
        return self._make_request("GET", "shipping", endpoint)

    # ==================== Claim Methods (OMS) ====================

    def get_claims(self, offset=0, limit=50, status=None):
        """Get all claims for this merchant.

        Args:
            offset: Pagination offset
            limit: Page size
            status: Optional status filter

        Returns:
            List of claim dicts
        """
        endpoint = f"/claims/merchantId/{self.merchant_id}"
        params = {"offset": offset, "limit": min(limit, 50)}
        if status:
            params["status"] = status
        return self._make_request("GET", "oms", endpoint, params=params)

    def accept_claim(
        self, claim_number, finalized_with="", invoice_link="", acception_reason=""
    ):
        """Accept a claim.

        Args:
            claim_number: Claim number
            finalized_with: Finalization type (e.g. "Refund", "Change")
            invoice_link: Invoice URL
            acception_reason: Reason for acceptance

        Returns:
            Response data
        """
        endpoint = f"/claims/number/{claim_number}/accept"
        json_data = {}
        if finalized_with:
            json_data["FinalizedWith"] = finalized_with
        if invoice_link:
            json_data["InvoiceLink"] = invoice_link
        if acception_reason:
            json_data["AcceptionReason"] = acception_reason
        return self._make_request("POST", "oms", endpoint, json_data=json_data)

    def reject_claim(self, claim_number, rejection_reason="", merchant_statement=""):
        """Reject a claim.

        Args:
            claim_number: Claim number
            rejection_reason: Reason for rejection
            merchant_statement: Merchant's statement

        Returns:
            Response data
        """
        endpoint = f"/claims/number/{claim_number}/reject"
        json_data = {}
        if rejection_reason:
            json_data["ClaimRejectionReason"] = rejection_reason
        if merchant_statement:
            json_data["MerchantStatement"] = merchant_statement
        return self._make_request("POST", "oms", endpoint, json_data=json_data)

    # ==================== Finance Methods ====================

    def get_transactions(
        self,
        record_date_start=None,
        record_date_end=None,
        transaction_types=None,
        offset=0,
        limit=100,
    ):
        """Get financial transactions from the accounting API.

        Args:
            record_date_start: Start date string (YYYY-MM-DD)
            record_date_end: End date string (YYYY-MM-DD)
            transaction_types: Comma-separated types (e.g. "Payment,Commission")
            offset: Pagination offset
            limit: Page size (max 100)

        Returns:
            Dict with transaction records
        """
        endpoint = f"/transactions/merchantid/{self.merchant_id}"
        params = {
            "offset": offset,
            "limit": min(limit, 100),
        }
        if record_date_start:
            params["recordDateStart"] = record_date_start
        if record_date_end:
            params["recordDateEnd"] = record_date_end
        if transaction_types:
            params["transactionTypes"] = transaction_types

        return self._make_request("GET", "finance", endpoint, params=params)

    # ==================== Ask to Seller (Questions) Methods ====================

    def get_issues(self, current_page=1, page_size=50):
        """Get customer questions (issues) list.

        Args:
            current_page: Page number (1-based)
            page_size: Number of items per page

        Returns:
            Dict with issues list and pagination info
        """
        endpoint = "/api/v1.0/issues"
        params = {"currentPage": current_page, "pageSize": page_size}
        return self._make_request("GET", "asktoseller", endpoint, params=params)

    def get_issue_detail(self, issue_number):
        """Get issue detail with conversation history.

        Args:
            issue_number: Issue number from HB

        Returns:
            Dict with issue detail and conversations
        """
        endpoint = f"/api/v1.0/issues/{issue_number}"
        return self._make_request("GET", "asktoseller", endpoint)

    def answer_issue(self, issue_number, answer_text):
        """Answer a customer question using multipart/form-data.

        Args:
            issue_number: Issue number
            answer_text: Answer text to send

        Returns:
            Response data
        """
        self.rate_limiter.acquire()

        base_url = self.service_urls.get("asktoseller")
        if not base_url:
            raise HepsiburadaAPIError("AskToSeller service URL not configured")

        url = f"{base_url}/api/v1.0/issues/{issue_number}/answer"
        headers = {
            "Authorization": self.auth_header,
            "User-Agent": self.user_agent,
            "merchantId": self.merchant_id,
        }

        _logger.debug("HB API POST %s (multipart/form-data)", url)

        try:
            response = requests.post(
                url=url,
                headers=headers,
                data={"Answer": answer_text},
                timeout=60,
            )
        except requests.RequestException as e:
            raise HepsiburadaAPIError(f"Request failed: {str(e)}") from e

        _logger.debug(
            "HB API response: %s - %s",
            response.status_code,
            response.text[:500] if response.text else "",
        )

        if response.status_code in (200, 201, 204):
            try:
                return response.json() if response.text else {}
            except json.JSONDecodeError:
                return {"raw": response.text}

        try:
            error_data = response.json()
            error_msg = error_data.get("message", response.text)
        except json.JSONDecodeError:
            error_data = None
            error_msg = response.text

        raise HepsiburadaAPIError(
            f"API error ({response.status_code}): {error_msg}",
            status_code=response.status_code,
            response_data=error_data,
        )

    # ==================== Utility Methods ====================

    def test_connection(self):
        """Test API connection by fetching paid orders with limit=1.

        Returns:
            True if connection successful

        Raises:
            HepsiburadaAPIError: If connection fails
        """
        self.get_paid_orders(offset=0, limit=1)
        return True
