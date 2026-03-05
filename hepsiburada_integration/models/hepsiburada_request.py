# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import base64
import json
import logging

import requests

from odoo.addons.marketplace_integration_base.models.marketplace_request import (
    MarketplaceAPIError,
    MarketplaceRateLimiter,
)

_logger = logging.getLogger(__name__)

# Hepsiburada API base URLs per service
# Stage URLs contain "-sit"; remove it for production.
HEPSIBURADA_API_URLS = {
    "mpop": {
        "stage": "https://mpop-sit.hepsiburada.com",
        "prod": "https://mpop.hepsiburada.com",
    },
    "listing": {
        "stage": "https://listing-external-sit.hepsiburada.com",
        "prod": "https://listing-external.hepsiburada.com",
    },
    "oms": {
        "stage": "https://oms-external-sit.hepsiburada.com",
        "prod": "https://oms-external.hepsiburada.com",
    },
    "shipping": {
        "stage": "https://shipping-external-sit.hepsiburada.com",
        "prod": "https://shipping-external.hepsiburada.com",
    },
    "asktoseller": {
        "stage": "https://api-asktoseller-merchant-sit.hepsiburada.com",
        "prod": "https://api-asktoseller-merchant.hepsiburada.com",
    },
    "claim": {
        "stage": "https://claim-external-sit.hepsiburada.com",
        "prod": "https://claim-external.hepsiburada.com",
    },
    "finance": {
        "stage": "https://finance-sit.hepsiburada.com",
        "prod": "https://finance.hepsiburada.com",
    },
}


class HepsiburadaAPIError(MarketplaceAPIError):
    """Exception raised for Hepsiburada API errors."""


class HepsiburadaRateLimiter(MarketplaceRateLimiter):
    """Rate limiter for Hepsiburada API (100 requests per second)."""

    def __init__(self):
        super().__init__(max_requests=100, time_window=1)


class HepsiburadaRequest:
    """API client for Hepsiburada marketplace integration.

    Handles authentication, rate limiting, and all API communication.
    Auth: HTTP Basic Auth (username:password in Authorization header).

    Services:
        mpop     - Catalog: categories, product upload, tracking
        listing  - Listing: stock/price updates, activate/deactivate
        oms      - Orders: order fetch, packages, invoice, labels, cancel
        shipping - Cargo: cargo firms
        asktoseller - Q&A: customer questions
        claim    - Claims: returns / disputes
        finance  - Accounting: transactions, performance
    """

    def __init__(
        self, merchant_id, username, password, user_agent=None, environment="stage"
    ):
        self.merchant_id = merchant_id
        self.environment = environment
        self.user_agent = user_agent or ""
        self.rate_limiter = HepsiburadaRateLimiter()

        auth_string = f"{username}:{password}"
        auth_b64 = base64.b64encode(auth_string.encode("utf-8")).decode("utf-8")
        self.auth_header = f"Basic {auth_b64}"

    # ── helpers ──────────────────────────────────────────────────────────

    def _get_base_url(self, service):
        """Return base URL for the given service and current environment."""
        urls = HEPSIBURADA_API_URLS.get(service, {})
        return urls.get(self.environment, urls.get("stage", ""))

    def _get_headers(self, content_type="application/json"):
        headers = {
            "Authorization": self.auth_header,
            "Content-Type": content_type,
            "Accept": "application/json",
        }
        if self.user_agent:
            headers["User-Agent"] = self.user_agent
        return headers

    def _handle_response(self, response):
        """Parse API response; raise on error."""
        # Rate-limit warning
        remaining = response.headers.get("X-RateLimit-Remaining")
        if remaining and int(remaining) < 50:
            _logger.warning("Hepsiburada rate limit low: %s remaining", remaining)

        # Success
        if response.status_code in (200, 201, 202, 204):
            if not response.text:
                return {}
            try:
                return response.json()
            except json.JSONDecodeError:
                return {"raw": response.text}

        # Rate-limit exceeded
        if response.status_code == 429:
            raise HepsiburadaAPIError(
                "Rate limit exceeded.",
                status_code=429,
                response_data={"reset": response.headers.get("X-RateLimit-Reset")},
            )

        # Error
        try:
            error_data = response.json()
            error_msg = error_data.get("message", response.text)
            if "errors" in error_data:
                errors = error_data["errors"]
                if isinstance(errors, list):
                    error_msg = "; ".join(
                        e.get("message", str(e)) if isinstance(e, dict) else str(e)
                        for e in errors
                    )
        except json.JSONDecodeError:
            error_data = None
            error_msg = response.text

        raise HepsiburadaAPIError(
            f"API error ({response.status_code}): {error_msg}",
            status_code=response.status_code,
            response_data=error_data,
        )

    def _make_request(
        self, method, url, params=None, json_data=None, skip_rate_limit=False
    ):
        """JSON request with rate limiting and error handling."""
        if not skip_rate_limit:
            self.rate_limiter.acquire()

        _logger.debug("HB API %s %s params=%s body=%s", method, url, params, json_data)

        try:
            response = requests.request(
                method=method,
                url=url,
                headers=self._get_headers(),
                params=params,
                json=json_data,
                timeout=60,
            )
        except requests.RequestException as e:
            raise HepsiburadaAPIError(f"Request failed: {e}") from e

        _logger.debug(
            "HB API response %s %s",
            response.status_code,
            response.text[:500] if response.text else "",
        )
        return self._handle_response(response)

    def _make_file_request(self, url, file_data, filename="products.json"):
        """Multipart/form-data file upload (used for catalog product import)."""
        self.rate_limiter.acquire()

        if isinstance(file_data, str):
            file_data = file_data.encode("utf-8")

        headers = {
            "Authorization": self.auth_header,
            "Accept": "application/json",
        }
        if self.user_agent:
            headers["User-Agent"] = self.user_agent
        files = {"file": (filename, file_data, "application/json")}

        _logger.debug("HB API file upload POST %s", url)

        try:
            response = requests.post(url=url, headers=headers, files=files, timeout=120)
        except requests.RequestException as e:
            raise HepsiburadaAPIError(f"File upload failed: {e}") from e

        _logger.debug(
            "HB API file upload response %s %s",
            response.status_code,
            response.text[:500] if response.text else "",
        )
        return self._handle_response(response)

    # ── mpop · Categories ────────────────────────────────────────────────

    def get_categories(
        self, leaf=True, status="ACTIVE", available=True, page=0, size=1000
    ):
        """GET /product/api/categories/get-all-categories

        Returns paginated flat list of leaf/active/available categories.
        Defaults match the recommended query: leaf=true&status=ACTIVE&available=true.
        """
        url = f"{self._get_base_url('mpop')}/product/api/categories/get-all-categories"
        params = {"version": 1, "page": page, "size": size}
        if leaf is not None:
            params["leaf"] = str(leaf).lower()
        if status:
            params["status"] = status
        if available is not None:
            params["available"] = str(available).lower()
        return self._make_request("GET", url, params=params)

    def get_category_attributes(self, category_id):
        """GET /product/api/categories/{categoryId}/attributes?version=2"""
        url = (
            f"{self._get_base_url('mpop')}"
            f"/product/api/categories/{category_id}/attributes"
        )
        return self._make_request("GET", url, params={"version": 2})

    def get_attribute_values(self, category_id, attribute_id):
        """GET /product/api/categories/{categoryId}/attribute/{attributeId}/values

        Returns list of {id, value} dicts for enum-type attributes.
        """
        url = (
            f"{self._get_base_url('mpop')}"
            f"/product/api/categories/{category_id}"
            f"/attribute/{attribute_id}/values"
        )
        return self._make_request("GET", url)

    # ── mpop · Products (catalog upload) ─────────────────────────────────

    def upload_products(self, items):
        """POST /product/api/products/import  (multipart/form-data JSON file)

        Each item: {categoryId, merchant, attributes: {merchantSku, Barcode, …}}
        Returns dict with trackingId.
        """
        url = f"{self._get_base_url('mpop')}/product/api/products/import"
        file_content = json.dumps(items, ensure_ascii=False)
        _logger.info("HB product upload payload: %s", file_content[:2000])
        return self._make_file_request(url, file_content)

    def get_product_tracking_status(self, tracking_id, page=0, size=1000):
        """GET /product/api/products/status/{trackingId}"""
        url = f"{self._get_base_url('mpop')}/product/api/products/status/{tracking_id}"
        return self._make_request(
            "GET", url, params={"version": 1, "page": page, "size": size}
        )

    def get_products_by_merchant(self, page=0, size=20):
        """GET /product/api/products/all-products-of-merchant/{merchantId}

        Only returns products uploaded via catalog API. Paginated.
        """
        url = (
            f"{self._get_base_url('mpop')}"
            f"/product/api/products/all-products-of-merchant/{self.merchant_id}"
        )
        params = {"page": page, "size": size}
        return self._make_request("GET", url, params=params)

    def get_products_by_status(self, status, offset=0, limit=100):
        """GET /product/api/products/status/{status}

        Status: WAITING, MISSING_INFO, MATCHED, PRE_MATCHED, etc.
        """
        url = f"{self._get_base_url('mpop')}/product/api/products/status/{status}"
        return self._make_request("GET", url, params={"offset": offset, "limit": limit})

    def approve_matched_products(self, listing_ids):
        """POST /product/api/products/approve"""
        url = f"{self._get_base_url('mpop')}/product/api/products/approve"
        return self._make_request("POST", url, json_data={"listingIds": listing_ids})

    def reject_matched_products(self, listing_ids):
        """POST /product/api/products/reject"""
        url = f"{self._get_base_url('mpop')}/product/api/products/reject"
        return self._make_request("POST", url, json_data={"listingIds": listing_ids})

    def delete_pending_products(self, merchant_skus):
        """POST /product/api/products/delete"""
        url = f"{self._get_base_url('mpop')}/product/api/products/delete"
        return self._make_request(
            "POST", url, json_data={"merchantSkus": merchant_skus}
        )

    def get_batch_request_result(self, tracking_id):
        """GET /product/api/products/status/{trackingId}

        Used to check status of a catalog product upload batch.
        Alias for get_product_tracking_status for batch request polling.
        """
        return self.get_product_tracking_status(tracking_id)

    # ── listing · Listing management ─────────────────────────────────────

    def get_listings(self, merchant_sku=None, hb_sku=None, offset=0, limit=100):
        """GET /listings/merchantid/{merchantId}"""
        url = f"{self._get_base_url('listing')}/listings/merchantid/{self.merchant_id}"
        params = {"offset": offset, "limit": limit}
        if merchant_sku:
            params["merchantSku"] = merchant_sku
        if hb_sku:
            params["hepsiburadaSku"] = hb_sku
        return self._make_request("GET", url, params=params)

    def update_listing_stock(self, items):
        """POST /listings/merchantid/{merchantId}/stock-uploads

        Items: [{HepsiburadaSku, MerchantSku, AvailableStock}]
        """
        url = (
            f"{self._get_base_url('listing')}"
            f"/listings/merchantid/{self.merchant_id}/stock-uploads"
        )
        return self._make_request("POST", url, json_data=items)

    def update_listing_price(self, items):
        """POST /listings/merchantid/{merchantId}/price-uploads

        Items: [{HepsiburadaSku, MerchantSku, Price}]
        """
        url = (
            f"{self._get_base_url('listing')}"
            f"/listings/merchantid/{self.merchant_id}/price-uploads"
        )
        return self._make_request("POST", url, json_data=items)

    def update_listing_inventory(self, items):
        """POST /listings/merchantid/{merchantId}/inventory-uploads

        Combined stock + price update. Max 5 concurrent pending operations.
        Items: [{HepsiburadaSku, MerchantSku, AvailableStock, Price}]
        """
        url = (
            f"{self._get_base_url('listing')}"
            f"/listings/merchantid/{self.merchant_id}/inventory-uploads"
        )
        return self._make_request("POST", url, json_data=items)

    def get_listing_update_status(self, upload_id, update_type="inventory"):
        """GET /listings/merchantid/{merchantId}/{type}-uploads/id/{uploadId}

        update_type: 'inventory', 'stock', or 'price'.
        """
        url = (
            f"{self._get_base_url('listing')}"
            f"/listings/merchantid/{self.merchant_id}"
            f"/{update_type}-uploads/id/{upload_id}"
        )
        return self._make_request("GET", url)

    def activate_listing(self, merchant_sku):
        """POST /listings/merchantid/{merchantId}/sku/{sku}/activate"""
        url = (
            f"{self._get_base_url('listing')}"
            f"/listings/merchantid/{self.merchant_id}"
            f"/sku/{merchant_sku}/activate"
        )
        return self._make_request("POST", url)

    def deactivate_listing(self, merchant_sku):
        """POST /listings/merchantid/{merchantId}/sku/{sku}/deactivate"""
        url = (
            f"{self._get_base_url('listing')}"
            f"/listings/merchantid/{self.merchant_id}"
            f"/sku/{merchant_sku}/deactivate"
        )
        return self._make_request("POST", url)

    def delete_listing(self, merchant_sku):
        """DELETE /listings/merchantid/{merchantId}/sku/{sku}"""
        url = (
            f"{self._get_base_url('listing')}"
            f"/listings/merchantid/{self.merchant_id}"
            f"/sku/{merchant_sku}"
        )
        return self._make_request("DELETE", url)

    # ── oms · Orders ─────────────────────────────────────────────────────

    def get_paid_orders(self, offset=0, limit=10, begin_date=None, end_date=None):
        """GET /orders/merchantid/{merchantId}

        Returns Open + Unpacked orders. Limit max 10.
        """
        url = f"{self._get_base_url('oms')}/orders/merchantid/{self.merchant_id}"
        params = {"offset": offset, "limit": min(limit, 10)}
        if begin_date:
            params["beginDate"] = begin_date
        if end_date:
            params["endDate"] = end_date
        return self._make_request("GET", url, params=params)

    def get_order_detail(self, order_number):
        """GET /orders/merchantid/{merchantId}/ordernumber/{orderNumber}"""
        url = (
            f"{self._get_base_url('oms')}"
            f"/orders/merchantid/{self.merchant_id}"
            f"/ordernumber/{order_number}"
        )
        return self._make_request("GET", url)

    def get_cancelled_orders(self, offset=0, limit=50, begin_date=None, end_date=None):
        """GET /orders/merchantid/{merchantId}/cancelled

        Last 1 month only. Limit max 50.
        """
        url = (
            f"{self._get_base_url('oms')}"
            f"/orders/merchantid/{self.merchant_id}/cancelled"
        )
        params = {"offset": offset, "limit": min(limit, 50)}
        if begin_date:
            params["beginDate"] = begin_date
        if end_date:
            params["endDate"] = end_date
        return self._make_request("GET", url, params=params)

    def get_payment_awaiting_orders(
        self, offset=0, limit=50, begin_date=None, end_date=None
    ):
        """GET /orders/merchantid/{merchantId}/paymentawaiting

        Returns orders awaiting payment. Limit max 50.
        """
        url = (
            f"{self._get_base_url('oms')}"
            f"/orders/merchantid/{self.merchant_id}/paymentawaiting"
        )
        params = {"offset": offset, "limit": min(limit, 50)}
        if begin_date:
            params["beginDate"] = begin_date
        if end_date:
            params["endDate"] = end_date
        return self._make_request("GET", url, params=params)

    def get_packageable_items(self, line_item_id):
        """GET /lineitems/merchantid/{merchantId}/packageablewith/lineitemid/{id}"""
        url = (
            f"{self._get_base_url('oms')}"
            f"/lineitems/merchantid/{self.merchant_id}"
            f"/packageablewith/lineitemid/{line_item_id}"
        )
        return self._make_request("GET", url)

    # ── oms · Packages ───────────────────────────────────────────────────

    def create_package(
        self, line_item_requests, package_number, parcel_quantity=None, deci=None
    ):
        """POST /packages/merchantid/{merchantId}"""
        url = f"{self._get_base_url('oms')}/packages/merchantid/{self.merchant_id}"
        data = {
            "lineItemRequests": line_item_requests,
            "packageNumber": package_number,
        }
        if parcel_quantity:
            data["parcelQuantity"] = parcel_quantity
        if deci:
            data["deci"] = deci
        return self._make_request("POST", url, json_data=data)

    def get_packages(
        self, offset=0, limit=10, begin_date=None, end_date=None, timespan=None
    ):
        """GET /packages/merchantid/{merchantId}

        24h date range max. Limit max 10.
        """
        url = f"{self._get_base_url('oms')}/packages/merchantid/{self.merchant_id}"
        params = {"offset": offset, "limit": min(limit, 10)}
        if begin_date:
            params["beginDate"] = begin_date
        if end_date:
            params["endDate"] = end_date
        if timespan:
            params["timespan"] = timespan
        return self._make_request("GET", url, params=params)

    def get_shipped_packages(
        self, offset=0, limit=10, begin_date=None, end_date=None, timespan=None
    ):
        """GET /packages/merchantid/{merchantId}/shipped

        Same pagination as get_packages(). Returns packages in transit.
        """
        url = (
            f"{self._get_base_url('oms')}"
            f"/packages/merchantid/{self.merchant_id}/shipped"
        )
        params = {"offset": offset, "limit": min(limit, 10)}
        if begin_date:
            params["beginDate"] = begin_date
        if end_date:
            params["endDate"] = end_date
        if timespan:
            params["timespan"] = timespan
        return self._make_request("GET", url, params=params)

    def get_delivered_packages(
        self, offset=0, limit=10, begin_date=None, end_date=None, timespan=None
    ):
        """GET /packages/merchantid/{merchantId}/delivered

        Same pagination as get_packages(). Returns delivered packages.
        """
        url = (
            f"{self._get_base_url('oms')}"
            f"/packages/merchantid/{self.merchant_id}/delivered"
        )
        params = {"offset": offset, "limit": min(limit, 10)}
        if begin_date:
            params["beginDate"] = begin_date
        if end_date:
            params["endDate"] = end_date
        if timespan:
            params["timespan"] = timespan
        return self._make_request("GET", url, params=params)

    def get_package_detail(self, package_number):
        """GET /packages/merchantid/{merchantId}/packagenumber/{packageNumber}"""
        url = (
            f"{self._get_base_url('oms')}"
            f"/packages/merchantid/{self.merchant_id}"
            f"/packagenumber/{package_number}"
        )
        return self._make_request("GET", url)

    def set_package_intransit(self, data):
        """POST .../packagenumber/{packageNumber}/intransit

        data: {shippedDate, packageNumber, barcode, trackingInfoCode, …}
        """
        url = (
            f"{self._get_base_url('oms')}"
            f"/packages/merchantid/{self.merchant_id}"
            f"/packagenumber/{data['packageNumber']}/intransit"
        )
        return self._make_request("POST", url, json_data=data)

    def set_package_delivered(self, data):
        """POST .../packagenumber/{packageNumber}/deliver

        data: {receivedDate, receivedBy, packageNumber, barcode}
        """
        url = (
            f"{self._get_base_url('oms')}"
            f"/packages/merchantid/{self.merchant_id}"
            f"/packagenumber/{data['packageNumber']}/deliver"
        )
        return self._make_request("POST", url, json_data=data)

    # ── oms · Invoice & Labels ───────────────────────────────────────────

    def upload_invoice_link(self, package_number, invoice_link):
        """PUT .../packagenumber/{packageNumber}/invoice

        Invoice must be PDF or HTML content-type.
        """
        url = (
            f"{self._get_base_url('oms')}"
            f"/packages/merchantid/{self.merchant_id}"
            f"/packagenumber/{package_number}/invoice"
        )
        return self._make_request("PUT", url, json_data={"invoiceLink": invoice_link})

    def get_package_labels(self, package_number, fmt="pdf"):
        """GET .../packagenumber/{packageNumber}/labels

        fmt: pdf, zpl, png, jpg.  Only HepsiJet + Aras support mutual barcodes.
        """
        url = (
            f"{self._get_base_url('oms')}"
            f"/packages/merchantid/{self.merchant_id}"
            f"/packagenumber/{package_number}/labels"
        )
        return self._make_request("GET", url, params={"format": fmt})

    # ── oms · Cancellation ───────────────────────────────────────────────

    def cancel_line_item(self, line_item_id):
        """POST /lineitems/merchantid/{merchantId}/id/{lineId}/cancelbymerchant

        Daily limit: 100. Only for Open status items.
        """
        url = (
            f"{self._get_base_url('oms')}"
            f"/lineitems/merchantid/{self.merchant_id}"
            f"/id/{line_item_id}/cancelbymerchant"
        )
        return self._make_request("POST", url)

    # ── shipping · Cargo ─────────────────────────────────────────────────

    def get_cargo_firms(self):
        """GET /cargoFirms/{merchantId}"""
        url = f"{self._get_base_url('shipping')}/cargoFirms/{self.merchant_id}"
        return self._make_request("GET", url)

    # ── asktoseller · Questions ──────────────────────────────────────────

    def get_questions(self, status=None, sort_by=0, offset=0, limit=50):
        """GET /api/v1.0/issues

        status: list of ints — 1=WaitingForAnswer, 2=Answered,
                3=Rejected, 4=AutoClosed.
        sort_by: 0=by question date, 1=by last update.
        """
        url = f"{self._get_base_url('asktoseller')}/api/v1.0/issues"
        params = {"sortBy": sort_by, "offset": offset, "limit": limit}
        if status:
            params["status"] = status  # requests handles list → repeated params
        return self._make_request("GET", url, params=params)

    def get_question_detail(self, question_number):
        """GET /api/v1.0/issues/{number}"""
        url = f"{self._get_base_url('asktoseller')}/api/v1.0/issues/{question_number}"
        return self._make_request("GET", url)

    def answer_question(self, question_number, answer_text):
        """POST /api/v1.0/issues/{number}/answer

        Sellers have 1 business day to respond.
        """
        url = (
            f"{self._get_base_url('asktoseller')}"
            f"/api/v1.0/issues/{question_number}/answer"
        )
        return self._make_request("POST", url, json_data={"answer": answer_text})

    def report_question(self, question_number, reason):
        """POST /api/v1.0/issues/{number}/report"""
        url = (
            f"{self._get_base_url('asktoseller')}"
            f"/api/v1.0/issues/{question_number}/report"
        )
        return self._make_request("POST", url, json_data={"reason": reason})

    def get_question_count_by_status(self):
        """GET /api/v1.0/issues/count"""
        url = f"{self._get_base_url('asktoseller')}/api/v1.0/issues/count"
        return self._make_request("GET", url)

    # ── claim · Claims / Returns ─────────────────────────────────────────

    def get_claims(self, offset=0, limit=50, begin_date=None, end_date=None):
        """GET /claims/{merchantid}"""
        url = f"{self._get_base_url('claim')}/claims/{self.merchant_id}"
        params = {"offset": offset, "limit": limit}
        if begin_date:
            params["begindate"] = begin_date
        if end_date:
            params["enddate"] = end_date
        return self._make_request("GET", url, params=params)

    def get_claims_by_status(self, status, offset=0, limit=50):
        """GET /claims/{merchantid}/status/{status}

        Statuses: NewRequest, AwaitingAction, InDispute,
                  Accepted, Rejected, Refunded, Cancelled.
        """
        url = f"{self._get_base_url('claim')}/claims/{self.merchant_id}/status/{status}"
        return self._make_request("GET", url, params={"offset": offset, "limit": limit})

    def accept_claim(self, claim_number):
        """POST /claims/number/{claimnumber}/accept"""
        url = f"{self._get_base_url('claim')}/claims/number/{claim_number}/accept"
        return self._make_request("POST", url)

    def reject_claim(self, claim_number, rejection_reason):
        """POST /claims/number/{claimnumber}/reject"""
        url = f"{self._get_base_url('claim')}/claims/number/{claim_number}/reject"
        return self._make_request(
            "POST", url, json_data={"ClaimRejectionReason": rejection_reason}
        )

    # ── finance · Accounting / Settlements ───────────────────────────────

    def get_transactions(
        self,
        offset=0,
        limit=100,
        record_date_start=None,
        record_date_end=None,
        transaction_types=None,
        order_number=None,
        status=None,
    ):
        """GET /transactions/{merchantid}

        transaction_types: Commission, Payment, etc.
        status: Paid, WillBePaid.  limit max 100.
        """
        url = f"{self._get_base_url('finance')}/transactions/{self.merchant_id}"
        params = {"offset": offset, "limit": min(limit, 100)}
        if record_date_start:
            params["recordDateStart"] = record_date_start
        if record_date_end:
            params["recordDateEnd"] = record_date_end
        if transaction_types:
            params["transactionTypes"] = transaction_types
        if order_number:
            params["orderNumber"] = order_number
        if status:
            params["status"] = status
        return self._make_request("GET", url, params=params)

    def get_performance(
        self,
        offset=0,
        limit=100,
        order_date_start=None,
        order_date_end=None,
        order_number=None,
        sku=None,
    ):
        """GET /orders/{merchantid}

        Returns net profit, revenue, expense by order/product.  limit max 100.
        """
        url = f"{self._get_base_url('finance')}/orders/{self.merchant_id}"
        params = {"offset": offset, "limit": min(limit, 100)}
        if order_date_start:
            params["orderDateStart"] = order_date_start
        if order_date_end:
            params["orderDateEnd"] = order_date_end
        if order_number:
            params["orderNumber"] = order_number
        if sku:
            params["sku"] = sku
        return self._make_request("GET", url, params=params)

    # ── utility ──────────────────────────────────────────────────────────

    def test_connection(self):
        """Test API connection by fetching first page of categories."""
        self.get_categories()
        return True
