# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class TrendyolWebhookController(http.Controller):
    """Controller for Trendyol webhook endpoints."""

    @http.route(
        "/ty/wh/<int:backend_id>",
        type="http",
        auth="none",
        methods=["POST"],
        csrf=False,
    )
    def webhook(self, backend_id):
        """Handle incoming webhooks from Trendyol.

        Trendyol authenticates via the x-api-key header (API_KEY auth type).

        Args:
            backend_id: ID of the trendyol.backend record

        Returns:
            JSON response
        """
        try:
            # Get backend
            backend = request.env["trendyol.backend"].sudo().browse(backend_id)
            if not backend.exists() or not backend.active:
                _logger.warning("Webhook received for unknown backend: %s", backend_id)
                return request.make_json_response(
                    {"status": "error", "message": "Unknown backend"}, status=404
                )

            # Get request data
            data = request.get_json_data()
            if not data:
                _logger.warning("Empty webhook data received")
                return request.make_json_response(
                    {"status": "error", "message": "Empty data"}, status=400
                )

            # Fail closed: this public endpoint must always have API-key auth.
            api_key = request.httprequest.headers.get("x-api-key")
            if not backend.webhook_api_key or api_key != backend.webhook_api_key:
                _logger.warning("Invalid webhook API key for backend %s", backend_id)
                return request.make_json_response(
                    {"status": "error", "message": "Invalid API key"}, status=401
                )

            # Process webhook
            self._process_webhook(backend, data)

            return request.make_json_response({"status": "success"})

        except (TypeError, ValueError):
            _logger.warning("Invalid JSON webhook payload for backend %s", backend_id)
            return request.make_json_response(
                {"status": "error", "message": "Invalid JSON payload"}, status=400
            )
        except Exception:
            _logger.exception("Error processing webhook for backend %s", backend_id)
            return request.make_json_response(
                {"status": "error", "message": "Internal error"}, status=500
            )

    def _process_webhook(self, backend, data):
        """Process webhook data.

        Args:
            backend: trendyol.backend record
            data: Dict of webhook data
        """
        packages = data.get("content") if isinstance(data, dict) else None
        package_count = len(packages) if isinstance(packages, list) else 1
        _logger.info(
            "Processing Trendyol webhook for backend %s (%d package(s))",
            backend.id,
            package_count,
        )

        # Queue processing via job
        backend.with_delay(
            channel="root.trendyol.webhook",
            description="Process Trendyol webhook",
        )._process_webhook_data(data)

    @http.route(
        "/ty/wh/<int:backend_id>/test",
        type="http",
        auth="user",
        methods=["GET"],
    )
    def webhook_test(self, backend_id):
        """Test endpoint to verify webhook URL is accessible.

        Args:
            backend_id: ID of the trendyol.backend record

        Returns:
            HTTP response
        """
        backend = request.env["trendyol.backend"].browse(backend_id)
        if not backend.exists():
            return request.make_response(
                "Backend not found",
                headers=[("Content-Type", "text/plain")],
            )

        return request.make_response(
            f"Webhook endpoint for {backend.name} is working",
            headers=[("Content-Type", "text/plain")],
        )
