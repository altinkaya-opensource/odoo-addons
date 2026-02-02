# Copyright 2025 Altinkaya Enclosures
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import base64
import json
import logging
import time
from collections import deque
from threading import Lock

import requests

_logger = logging.getLogger(__name__)

# Trendyol API endpoints (updated May 2025)
TRENDYOL_API_URLS = {
    "stage": "https://stageapigw.trendyol.com",
    "prod": "https://apigw.trendyol.com",
}


class TrendyolRateLimiter:
    """Rate limiter for Trendyol API (50 requests per 10 seconds)."""

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


class TrendyolAPIError(Exception):
    """Exception raised for Trendyol API errors."""

    def __init__(self, message, status_code=None, response_data=None):
        super().__init__(message)
        self.status_code = status_code
        self.response_data = response_data


class TrendyolRequest:
    """API client for Trendyol marketplace integration.

    Handles authentication, rate limiting, and all API communication.
    """

    def __init__(self, seller_id, api_key, api_secret, environment="stage"):
        """Initialize Trendyol API client.

        Args:
            seller_id: Trendyol seller ID
            api_key: API key from Trendyol seller panel
            api_secret: API secret from Trendyol seller panel
            environment: 'stage' for testing, 'prod' for production
        """
        self.seller_id = seller_id
        self.api_key = api_key
        self.api_secret = api_secret
        self.environment = environment
        self.base_url = TRENDYOL_API_URLS.get(environment, TRENDYOL_API_URLS["stage"])
        self.rate_limiter = TrendyolRateLimiter()

        # Build auth header
        auth_string = f"{api_key}:{api_secret}"
        auth_bytes = auth_string.encode("utf-8")
        auth_b64 = base64.b64encode(auth_bytes).decode("utf-8")
        self.auth_header = f"Basic {auth_b64}"

    def _get_headers(self):
        """Get common headers for API requests."""
        return {
            "Authorization": self.auth_header,
            "User-Agent": f"{self.seller_id} - SelfIntegration",
            "Content-Type": "application/json",
        }

    def _make_request(
        self, method, endpoint, params=None, json_data=None, skip_rate_limit=False
    ):
        """Make an API request with rate limiting and error handling.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            endpoint: API endpoint path
            params: Query parameters
            json_data: JSON body data
            skip_rate_limit: If True, skip rate limiting (for stock/price updates)

        Returns:
            Response JSON data

        Raises:
            TrendyolAPIError: If the API returns an error
        """
        if not skip_rate_limit:
            self.rate_limiter.acquire()

        url = f"{self.base_url}{endpoint}"
        headers = self._get_headers()

        _logger.debug(
            "Trendyol API %s %s - params: %s, body: %s",
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
            raise TrendyolAPIError(f"Request failed: {str(e)}") from e

        _logger.debug(
            "Trendyol API response: %s - %s",
            response.status_code,
            response.text[:500] if response.text else "",
        )

        # Handle response
        if response.status_code in (200, 201):
            try:
                return response.json() if response.text else {}
            except json.JSONDecodeError:
                return {"raw": response.text}

        # Handle errors
        try:
            error_data = response.json()
            error_msg = error_data.get("message", response.text)
            if "errors" in error_data:
                error_msg = "; ".join(
                    e.get("message", str(e)) for e in error_data["errors"]
                )
        except json.JSONDecodeError:
            error_data = None
            error_msg = response.text

        raise TrendyolAPIError(
            f"API error ({response.status_code}): {error_msg}",
            status_code=response.status_code,
            response_data=error_data,
        )

    # ==================== Brand Methods ====================

    def get_brands(self, page=0, size=1000):
        """Get list of Trendyol brands.

        Args:
            page: Page number (0-indexed)
            size: Page size (max 1000)

        Returns:
            Dict with 'brands' list and pagination info
        """
        endpoint = "/integration/product/brands"
        params = {"page": page, "size": min(size, 1000)}
        return self._make_request("GET", endpoint, params=params)

    def get_brands_by_name(self, name):
        """Search brands by name.

        Args:
            name: Brand name to search

        Returns:
            Dict with matching brands
        """
        endpoint = "/integration/product/brands/by-name"
        params = {"name": name}
        return self._make_request("GET", endpoint, params=params)

    # ==================== Category Methods ====================

    def get_categories(self):
        """Get full category tree.

        Returns:
            Dict with 'categories' list containing nested categories
        """
        endpoint = "/integration/product/product-categories"
        return self._make_request("GET", endpoint)

    def get_category_attributes(self, category_id):
        """Get attributes for a specific category.

        Args:
            category_id: Trendyol category ID

        Returns:
            Dict with 'categoryAttributes' list
        """
        endpoint = f"/integration/product/product-categories/{category_id}/attributes"
        return self._make_request("GET", endpoint)

    # ==================== Product Methods ====================

    def create_products(self, items):
        """Create products in Trendyol.

        Args:
            items: List of product data dicts (max 1000)

        Returns:
            Dict with 'batchRequestId' for tracking
        """
        if len(items) > 1000:
            raise TrendyolAPIError("Maximum 1000 items per batch")

        endpoint = f"/integration/product/sellers/{self.seller_id}/products"
        return self._make_request("POST", endpoint, json_data={"items": items})

    def update_products(self, items):
        """Update existing products in Trendyol.

        Args:
            items: List of product update data dicts (max 1000)

        Returns:
            Dict with 'batchRequestId' for tracking
        """
        if len(items) > 1000:
            raise TrendyolAPIError("Maximum 1000 items per batch")

        endpoint = f"/integration/product/sellers/{self.seller_id}/products"
        return self._make_request("PUT", endpoint, json_data={"items": items})

    def update_price_and_inventory(self, items):
        """Update product prices and inventory.

        Note: This endpoint has NO rate limit.

        Args:
            items: List of price/inventory update dicts

        Returns:
            Dict with 'batchRequestId' for tracking
        """
        endpoint = f"/integration/inventory/sellers/{self.seller_id}/products/price-and-inventory"
        return self._make_request(
            "POST", endpoint, json_data={"items": items}, skip_rate_limit=True
        )

    def get_batch_request_result(self, batch_request_id):
        """Get result of a batch request.

        Args:
            batch_request_id: ID returned from create/update operations

        Returns:
            Dict with batch status and item results
        """
        endpoint = f"/integration/product/sellers/{self.seller_id}/products/batch-requests/{batch_request_id}"
        return self._make_request("GET", endpoint)

    def filter_products(
        self,
        approved=None,
        barcode=None,
        start_date=None,
        end_date=None,
        page=0,
        size=50,
    ):
        """Filter and list products.

        Args:
            approved: Filter by approval status (True/False)
            barcode: Filter by barcode
            start_date: Start date (Unix timestamp ms)
            end_date: End date (Unix timestamp ms)
            page: Page number
            size: Page size (max 200)

        Returns:
            Dict with 'content' list and pagination info
        """
        endpoint = f"/integration/product/sellers/{self.seller_id}/products"
        params = {"page": page, "size": min(size, 200)}
        if approved is not None:
            params["approved"] = str(approved).lower()
        if barcode:
            params["barcode"] = barcode
        if start_date:
            params["startDate"] = start_date
        if end_date:
            params["endDate"] = end_date

        return self._make_request("GET", endpoint, params=params)

    def delete_products(self, items):
        """Delete products from Trendyol.

        Args:
            items: List of dicts with 'barcode' keys

        Returns:
            Dict with 'batchRequestId' for tracking
        """
        endpoint = f"/integration/product/sellers/{self.seller_id}/products"
        return self._make_request("DELETE", endpoint, json_data={"items": items})

    # ==================== Order Methods ====================

    def get_orders(
        self,
        status=None,
        start_date=None,
        end_date=None,
        order_number=None,
        page=0,
        size=200,
    ):
        """Get shipment packages (orders).

        Args:
            status: Filter by status (Created, Picking, Invoiced, Shipped, etc.)
            start_date: Start date (Unix timestamp ms)
            end_date: End date (Unix timestamp ms) - max 2 weeks range
            order_number: Filter by specific order number
            page: Page number
            size: Page size (max 200)

        Returns:
            Dict with 'content' list and pagination info
        """
        endpoint = f"/integration/order/sellers/{self.seller_id}/orders"
        params = {"page": page, "size": min(size, 200)}
        if status:
            params["status"] = status
        if start_date:
            params["startDate"] = start_date
        if end_date:
            params["endDate"] = end_date
        if order_number:
            params["orderNumber"] = order_number

        return self._make_request("GET", endpoint, params=params)

    def update_package_status(
        self, shipment_package_id, status, lines=None, params=None
    ):
        """Update package status.

        Args:
            shipment_package_id: Package ID
            status: New status (Picking, Invoiced, etc.)
            lines: List of dicts with 'lineId' and 'quantity'
            params: Additional parameters (invoiceNumber, etc.)

        Returns:
            Response data
        """
        endpoint = f"/integration/order/sellers/{self.seller_id}/shipment-packages/{shipment_package_id}"
        json_data = {"status": status}
        if lines:
            json_data["lines"] = lines
        if params:
            json_data["params"] = params
        return self._make_request("PUT", endpoint, json_data=json_data)

    def update_tracking_number(
        self, shipment_package_id, tracking_number, cargo_provider_id=None
    ):
        """Update tracking number for a package.

        Note: This endpoint is DEPRECATED. Use cargoTrackingNumber from
        getShipmentPackages instead for Trendyol contracted cargo.

        Args:
            shipment_package_id: Package ID
            tracking_number: Cargo tracking number
            cargo_provider_id: Optional cargo provider ID (unused in new API)

        Returns:
            Response data
        """
        endpoint = (
            f"/integration/order/sellers/{self.seller_id}/shipment-packages/"
            f"{shipment_package_id}/update-tracking-number"
        )
        json_data = {"trackingNumber": tracking_number}

        return self._make_request("PUT", endpoint, json_data=json_data)

    def cancel_order_items(self, shipment_package_id, lines, reason_id=None):
        """Cancel order line items.

        Args:
            shipment_package_id: Package ID
            lines: List of dicts with 'lineId' and 'quantity'
            reason_id: Cancellation reason ID (500=Stock Out, 501=Defective,
                       502=Incorrect Price, 504=Integration Problem,
                       505=Bulk purchase, 506=Force Majeure)

        Returns:
            Response data
        """
        endpoint = (
            f"/integration/order/sellers/{self.seller_id}/shipment-packages/"
            f"{shipment_package_id}/items/unsupplied"
        )
        json_data = {"lines": lines}
        if reason_id:
            json_data["reasonId"] = reason_id

        return self._make_request("PUT", endpoint, json_data=json_data)

    def split_shipment_package(self, shipment_package_id, order_line_ids):
        """Split a shipment package into multiple packages.

        Args:
            shipment_package_id: Original package ID
            order_line_ids: List of order line IDs to split into a new package

        Returns:
            Response data
        """
        endpoint = (
            f"/integration/order/sellers/{self.seller_id}/shipment-packages/"
            f"{shipment_package_id}/split"
        )
        return self._make_request(
            "POST", endpoint, json_data={"orderLineIds": order_line_ids}
        )

    # ==================== Invoice Methods ====================

    def send_invoice_link(
        self, shipment_package_id, invoice_link, invoice_number=None, invoice_date=None
    ):
        """Send invoice link to Trendyol.

        Args:
            shipment_package_id: Package ID
            invoice_link: Public URL to invoice PDF/HTML (must be accessible for 8 years)
            invoice_number: Invoice number (required for micro export orders)
                           Format: 3 alphanumeric + 13 numeric = 16 chars
            invoice_date: Invoice datetime as Unix timestamp (seconds or milliseconds)
                         (required for micro export orders)

        Returns:
            Response data
        """
        endpoint = f"/integration/sellers/{self.seller_id}/seller-invoice-links"
        json_data = {
            "invoiceLink": invoice_link,
            "shipmentPackageId": shipment_package_id,
        }
        if invoice_number:
            json_data["invoiceNumber"] = invoice_number
        if invoice_date:
            json_data["invoiceDateTime"] = invoice_date

        return self._make_request("POST", endpoint, json_data=json_data)

    # ==================== Webhook Methods ====================

    def create_webhook(
        self,
        webhook_url,
        subscribed_statuses=None,
        username=None,
        password=None,
        api_key=None,
        authentication_type="BASIC_AUTHENTICATION",
    ):
        """Create a webhook subscription.

        Args:
            webhook_url: URL to receive webhooks
            subscribed_statuses: List of statuses to subscribe to (e.g., CREATED, PICKING,
                                INVOICED, SHIPPED, CANCELLED, DELIVERED, etc.)
                                If empty, subscribes to all statuses.
            username: Username for BASIC_AUTHENTICATION
            password: Password for BASIC_AUTHENTICATION
            api_key: API key for API_KEY authentication (sent as x-api-key header)
            authentication_type: "BASIC_AUTHENTICATION" or "API_KEY"

        Returns:
            Response data with webhook ID
        """
        endpoint = f"/integration/webhook/sellers/{self.seller_id}/webhooks"
        json_data = {"url": webhook_url, "authenticationType": authentication_type}
        if subscribed_statuses:
            json_data["subscribedStatuses"] = subscribed_statuses
        if authentication_type == "BASIC_AUTHENTICATION" and username and password:
            json_data["username"] = username
            json_data["password"] = password
        elif authentication_type == "API_KEY" and api_key:
            json_data["apiKey"] = api_key

        return self._make_request("POST", endpoint, json_data=json_data)

    def get_webhooks(self):
        """Get list of registered webhooks.

        Returns:
            List of webhook configurations
        """
        endpoint = f"/integration/webhook/sellers/{self.seller_id}/webhooks"
        return self._make_request("GET", endpoint)

    def delete_webhook(self, webhook_id):
        """Delete a webhook subscription.

        Args:
            webhook_id: ID of webhook to delete

        Returns:
            Response data
        """
        endpoint = (
            f"/integration/webhook/sellers/{self.seller_id}/webhooks/{webhook_id}"
        )
        return self._make_request("DELETE", endpoint)

    # ==================== Claims/Returns Methods ====================

    def get_claims(
        self,
        start_date=None,
        end_date=None,
        claim_ids=None,
        claim_item_status=None,
        order_number=None,
        page=0,
        size=25,
    ):
        """Get claims (returns) from Trendyol.

        Args:
            start_date: Start date (Unix timestamp ms)
            end_date: End date (Unix timestamp ms)
            claim_ids: List of specific claim IDs to fetch
            claim_item_status: Filter by status (Created, WaitingInAction, Accepted,
                              Cancelled, Rejected, Unresolved, InAnalysis, WaitingFraudCheck)
            order_number: Filter by order number
            page: Page number
            size: Page size (max 25)

        Returns:
            Dict with 'content' list and pagination info
        """
        endpoint = f"/integration/order/sellers/{self.seller_id}/claims"
        params = {"page": page, "size": min(size, 25)}
        if start_date:
            params["startDate"] = start_date
        if end_date:
            params["endDate"] = end_date
        if claim_ids:
            params["claimIds"] = ",".join(str(c) for c in claim_ids)
        if claim_item_status:
            params["claimItemStatus"] = claim_item_status
        if order_number:
            params["orderNumber"] = order_number

        return self._make_request("GET", endpoint, params=params)

    def approve_claim(self, claim_id, claim_line_item_id_list):
        """Approve claim items.

        Note: Can only approve claims with "WaitingInAction" status.
        Approved claims may go to "WaitingFraudCheck" status before "Accepted".

        Args:
            claim_id: Claim ID
            claim_line_item_id_list: List of claim line item IDs to approve

        Returns:
            Response data
        """
        endpoint = f"/integration/order/sellers/{self.seller_id}/claims/{claim_id}/items/approve"
        json_data = {"claimLineItemIdList": claim_line_item_id_list, "params": {}}
        return self._make_request("PUT", endpoint, json_data=json_data)

    # ==================== Address Methods ====================

    def get_supplier_addresses(self):
        """Get supplier's registered addresses.

        Returns:
            Dict with address list
        """
        endpoint = f"/integration/sellers/{self.seller_id}/addresses"
        return self._make_request("GET", endpoint)

    # ==================== Customer Questions Methods ====================

    def get_questions(
        self,
        status=None,
        barcode=None,
        start_date=None,
        end_date=None,
        page=0,
        size=100,
    ):
        """Get customer questions.

        Args:
            status: Filter by status (WAITING_FOR_ANSWER, WAITING_FOR_APPROVE,
                   ANSWERED, REPORTED, REJECTED)
            barcode: Filter by product barcode
            start_date: Start date (Unix timestamp ms)
            end_date: End date (Unix timestamp ms) - max 2 weeks range
            page: Page number
            size: Page size

        Returns:
            Dict with questions list
        """
        endpoint = f"/integration/qna/sellers/{self.seller_id}/questions/filter"
        params = {"page": page, "size": size}
        if status:
            params["status"] = status
        if barcode:
            params["barcode"] = barcode
        if start_date:
            params["startDate"] = start_date
        if end_date:
            params["endDate"] = end_date

        return self._make_request("GET", endpoint, params=params)

    def answer_question(self, question_id, answer_text):
        """Answer a customer question.

        Args:
            question_id: Question ID
            answer_text: Answer text (min 10 chars, max 2000 chars)

        Returns:
            Response data
        """
        endpoint = (
            f"/integration/qna/sellers/{self.seller_id}/questions/{question_id}/answers"
        )
        json_data = {"text": answer_text[:2000]}
        return self._make_request("POST", endpoint, json_data=json_data)

    # ==================== Utility Methods ====================

    def test_connection(self):
        """Test API connection by fetching supplier addresses.

        Returns:
            True if connection successful

        Raises:
            TrendyolAPIError: If connection fails
        """
        self.get_supplier_addresses()
        return True
