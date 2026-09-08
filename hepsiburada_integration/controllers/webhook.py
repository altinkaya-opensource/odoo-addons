# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import logging
import secrets

from werkzeug.exceptions import BadRequest

from odoo import _, http
from odoo.http import request

_logger = logging.getLogger(__name__)


class HepsiburadaWebhookController(http.Controller):
    """Receive Hepsiburada notifications and refresh orders through the API."""

    @http.route(
        "/hb/wh/<int:backend_id>/orders",
        type="http",
        auth="none",
        methods=["POST"],
        csrf=False,
        save_session=False,
    )
    def create_orders(self, backend_id, **_kwargs):
        """Accept the Create Order contract."""
        return self._receive(backend_id, "orders")

    @http.route(
        "/hb/wh/<int:backend_id>/packages",
        type="http",
        auth="none",
        methods=["POST"],
        csrf=False,
        save_session=False,
    )
    def create_packages(self, backend_id, **_kwargs):
        """Accept the Create Packages contract."""
        return self._receive(backend_id, "packages")

    @http.route(
        "/hb/wh/<int:backend_id>/packages/<string:package_number>/<string:event>",
        type="http",
        auth="none",
        methods=["PUT"],
        csrf=False,
        save_session=False,
    )
    def package_event(self, backend_id, package_number, event, **_kwargs):
        """Accept package shipment, delivery, failure and unpack notifications."""
        if event not in ("intransit", "deliver", "undeliver", "unpack"):
            return request.make_response("", status=404)
        return self._receive(backend_id, event, package_number)

    @http.route(
        "/hb/wh/<int:backend_id>/lineitems/<string:line_item_id>/cancel",
        type="http",
        auth="none",
        methods=["PUT"],
        csrf=False,
        save_session=False,
    )
    def cancel_line(self, backend_id, line_item_id, **_kwargs):
        """Accept the Order Cancel contract."""
        return self._receive(backend_id, "cancel", line_item_id)

    @http.route(
        "/hb/wh/<int:backend_id>/orders/<string:order_number>/shippingaddress",
        type="http",
        auth="none",
        methods=["PUT"],
        csrf=False,
        save_session=False,
    )
    def shipping_address(self, backend_id, order_number, **_kwargs):
        """Accept the Change Shipping Address Order contract."""
        return self._receive(backend_id, "shippingaddress", order_number)

    def _receive(self, backend_id, event, resource_id=None):
        """Authenticate before reading data and acknowledge only durable jobs."""
        backend = request.env["hepsiburada.backend"].sudo().browse(backend_id).exists()
        auth = request.httprequest.authorization
        if not self._authorized(backend, auth):
            return request.make_response(
                "",
                status=401,
                headers=[("WWW-Authenticate", 'Basic realm="Hepsiburada"')],
            )

        try:
            data = request.get_json_data()
            if not self._valid_payload(backend, event, resource_id, data):
                return request.make_json_response(
                    {"error": _("Invalid payload")}, status=400
                )
        except (BadRequest, TypeError, ValueError):
            return request.make_json_response({"error": _("Invalid JSON")}, status=400)

        # Webhooks can arrive late or more than once. Fetch current API state
        # rather than applying their potentially stale order/address snapshots.
        backend.with_company(backend.company_id)._queue_webhook_sync()
        _logger.info("Accepted HB %s webhook for backend %s", event, backend.id)
        return request.make_response(
            "", status=201 if event in ("orders", "packages") else 204
        )

    @staticmethod
    def _authorized(backend, auth):
        """Require enabled, per-backend Basic Auth credentials."""
        if (
            not backend
            or not backend.active
            or not backend.webhook_enabled
            or not backend.webhook_username
            or not backend.webhook_password
            or not auth
            or auth.type.lower() != "basic"
        ):
            return False
        username_ok = secrets.compare_digest(
            (auth.username or "").encode(), backend.webhook_username.encode()
        )
        password_ok = secrets.compare_digest(
            (auth.password or "").encode(), backend.webhook_password.encode()
        )
        return username_ok and password_ok

    @staticmethod
    def _valid_payload(backend, event, resource_id, data):
        """Check contract identifiers and prevent cross-merchant notifications."""
        if not isinstance(data, dict):
            return False
        if "merchantId" in data and str(data["merchantId"]) != backend.merchant_id:
            return False
        if event == "shippingaddress":
            return (
                bool(data.get("addressId"))
                and str(data.get("orderNumber") or "") == resource_id
            )
        if event == "orders":
            items = data.get("items")
            return (
                bool(items)
                and isinstance(items, list)
                and all(
                    isinstance(item, dict)
                    and item.get("id")
                    and item.get("orderNumber")
                    and str(item.get("merchantId") or "") == backend.merchant_id
                    for item in items
                )
            )
        if str(data.get("merchantId") or "") != backend.merchant_id:
            return False
        if event == "packages":
            items = data.get("items")
            return (
                bool(data.get("packageNumber"))
                and isinstance(items, list)
                and bool(items)
                and all(
                    isinstance(item, dict)
                    and item.get("lineItemId")
                    and item.get("orderNumber")
                    for item in items
                )
            )
        key = "id" if event == "cancel" else "packageNumber"
        return str(data.get(key) or "") == resource_id
