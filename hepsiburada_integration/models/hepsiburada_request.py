# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import json
import logging

import requests

from odoo.addons.marketplace_integration_base.models.marketplace_request import (
    MarketplaceAPIError,
    MarketplaceRateLimiter,
    MarketplaceRequest,
)

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


class HepsiburadaRateLimiter(MarketplaceRateLimiter):
    """Rate limiter for Hepsiburada API (100 requests per second)."""


class HepsiburadaAPIError(MarketplaceAPIError):
    """Exception raised for Hepsiburada API errors."""


class HepsiburadaRequest(MarketplaceRequest):
    """API client for Hepsiburada marketplace integration.

    Handles authentication, rate limiting, and all API communication.
    Only implements OMS and Shipping endpoints needed for order import,
    invoice sending, and status updates.
    """

    api_name = "HB"
    success_status_codes = (200, 201, 204)
    error_class = HepsiburadaAPIError

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
        self.auth_header = self._build_basic_auth_header(username, password)

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
        base_url = self.service_urls.get(service)
        if not base_url:
            raise HepsiburadaAPIError(f"Unknown service: {service}")

        url = f"{base_url}{endpoint}"
        headers = self._get_headers()

        # AskToSeller API requires merchantId header on all requests
        if service == "asktoseller":
            headers["merchantId"] = self.merchant_id

        return self._request_json(
            method,
            url,
            headers,
            params,
            json_data,
        )

    # ==================== Order Methods (OMS) ====================

    @staticmethod
    def _date_range_params(begin_date=None, end_date=None):
        params = {}
        if begin_date:
            params["begindate"] = begin_date
        if end_date:
            params["enddate"] = end_date
        return params

    def get_paid_orders(self, offset=0, limit=50, begin_date=None, end_date=None):
        """Get paid orders (ready to process).

        Args:
            offset: Pagination offset
            limit: Page size (max 50)

        Returns:
            List of order line item dicts
        """
        endpoint = f"/orders/merchantid/{self.merchant_id}"
        params = {"offset": offset, "limit": min(limit, 100)}
        params.update(self._date_range_params(begin_date, end_date))
        return self._make_request("GET", "oms", endpoint, params=params)

    def get_packages(self, offset=0, limit=10, begin_date=None, end_date=None):
        """Get packages with full order data.

        Args:
            offset: Pagination offset
            limit: Page size (max 10)

        Returns:
            List of package dicts with nested items
        """
        endpoint = f"/packages/merchantid/{self.merchant_id}"
        params = {"offset": offset, "limit": min(limit, 10)}
        params.update(self._date_range_params(begin_date, end_date))
        return self._make_request("GET", "oms", endpoint, params=params)

    def get_shipped_packages(self, offset=0, limit=50, begin_date=None, end_date=None):
        """Get shipped (in transit) packages."""
        endpoint = f"/packages/merchantid/{self.merchant_id}/shipped"
        params = {"offset": offset, "limit": min(limit, 50)}
        params.update(self._date_range_params(begin_date, end_date))
        return self._make_request("GET", "oms", endpoint, params=params)

    def get_delivered_packages(
        self, offset=0, limit=50, begin_date=None, end_date=None
    ):
        """Get delivered packages."""
        endpoint = f"/packages/merchantid/{self.merchant_id}/delivered"
        params = {"offset": offset, "limit": min(limit, 50)}
        params.update(self._date_range_params(begin_date, end_date))
        return self._make_request("GET", "oms", endpoint, params=params)

    def get_undelivered_packages(
        self, offset=0, limit=50, begin_date=None, end_date=None
    ):
        """Get undelivered packages."""
        endpoint = f"/packages/merchantid/{self.merchant_id}/undelivered"
        params = {"offset": offset, "limit": min(limit, 50)}
        params.update(self._date_range_params(begin_date, end_date))
        return self._make_request("GET", "oms", endpoint, params=params)

    def get_cancelled_orders(self, offset=0, limit=50, begin_date=None, end_date=None):
        """Get cancelled orders."""
        endpoint = f"/orders/merchantid/{self.merchant_id}/cancelled"
        params = {"offset": offset, "limit": min(limit, 50)}
        params.update(self._date_range_params(begin_date, end_date))
        return self._make_request("GET", "oms", endpoint, params=params)

    def get_payment_awaiting_orders(
        self, offset=0, limit=50, begin_date=None, end_date=None
    ):
        """Get orders awaiting payment."""
        endpoint = f"/orders/merchantid/{self.merchant_id}/paymentawaiting"
        params = {"offset": offset, "limit": min(limit, 50)}
        params.update(self._date_range_params(begin_date, end_date))
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

    def get_package_label(self, package_number, label_format="pdf"):
        """Get shipping label (Ortak Barkod) PDF for a package.

        Cannot use _make_request() because the response is binary PDF,
        not JSON. Handles HTTP directly (same pattern as answer_issue).

        Args:
            package_number: Package number
            label_format: Label format, defaults to 'pdf'

        Returns:
            Raw bytes of the PDF label

        Raises:
            HepsiburadaAPIError: If the API returns an error
        """
        self.rate_limiter.acquire()

        base_url = self.service_urls.get("oms")
        if not base_url:
            raise HepsiburadaAPIError("OMS service URL not configured")

        endpoint = (
            f"/packages/merchantid/{self.merchant_id}"
            f"/packagenumber/{package_number}/labels"
        )
        url = f"{base_url}{endpoint}"
        headers = self._get_headers()
        headers["Accept"] = "application/pdf"

        _logger.debug("HB API GET %s (label)", url)

        try:
            response = requests.get(
                url=url,
                headers=headers,
                params={"format": label_format},
                timeout=60,
            )
        except requests.RequestException as e:
            raise HepsiburadaAPIError(f"Request failed: {str(e)}") from e

        if response.status_code == 200:
            return response.content

        try:
            error_data = response.json()
            error_msg = error_data.get("message", response.text)
        except (json.JSONDecodeError, ValueError):
            error_data = None
            error_msg = response.text

        raise HepsiburadaAPIError(
            f"Label API error ({response.status_code}): {error_msg}",
            status_code=response.status_code,
            response_data=error_data,
        )

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

    # ==================== Claim Methods (OMS) ====================

    def get_claims(
        self,
        offset=0,
        limit=50,
        status=None,
        begin_date=None,
        end_date=None,
    ):
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
        if begin_date:
            params["beginDate"] = begin_date
        if end_date:
            params["endDate"] = end_date
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

    def get_missing_invoice_packages(self, offset=0, limit=50):
        """Get packages with missing invoices.

        Args:
            offset: Pagination offset
            limit: Page size (max 50)

        Returns:
            Dict with items list and pagination info
        """
        endpoint = f"/packages/merchantid/{self.merchant_id}/missing-invoice"
        params = {"offset": offset, "limit": min(limit, 50)}
        return self._make_request("GET", "oms", endpoint, params=params)

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

    def get_issues(self, current_page=1, page_size=25, **filters):
        """Get customer questions (issues) list.

        Args:
            current_page: Page number (1-based)
            page_size: Number of items per page

        Returns:
            Dict with issues list and pagination info
        """
        endpoint = "/api/v1.0/issues"
        params = {
            "page": max(int(current_page or 1), 1),
            "size": min(max(int(page_size or 25), 1), 25),
            "desc": True,
        }
        params.update(
            {key: value for key, value in filters.items() if value is not None}
        )
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
            "Accept": "application/json",
        }

        _logger.debug("HB API POST %s (multipart/form-data)", url)

        try:
            response = requests.post(
                url=url,
                headers=headers,
                files={"Answer": (None, answer_text)},
                timeout=60,
            )
        except requests.RequestException as e:
            raise HepsiburadaAPIError(f"Request failed: {str(e)}") from e

        _logger.debug("HB AskToSeller API response status: %s", response.status_code)

        if response.status_code in (200, 201, 204):
            try:
                return response.json() if response.text else {}
            except json.JSONDecodeError:
                return {"raw": response.text}

        try:
            error_data = response.json()
            error_msg = (
                self._extract_error_message(error_data, response.text)
                if isinstance(error_data, dict)
                else response.text
            )
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
