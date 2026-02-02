# Copyright 2025 Altinkaya Enclosures
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import hashlib
import hmac
import json
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class TrendyolWebhookController(http.Controller):
    """Controller for Trendyol webhook endpoints."""

    @http.route(
        "/trendyol/webhook/<int:backend_id>",
        type="json",
        auth="none",
        methods=["POST"],
        csrf=False,
    )
    def webhook(self, backend_id):
        """Handle incoming webhooks from Trendyol.

        Args:
            backend_id: ID of the trendyol.backend record

        Returns:
            JSON response
        """
        try:
            # Get backend
            backend = request.env["trendyol.backend"].sudo().browse(backend_id)
            if not backend.exists():
                _logger.warning("Webhook received for unknown backend: %s", backend_id)
                return {"status": "error", "message": "Unknown backend"}

            # Get request data
            data = request.jsonrequest
            if not data:
                _logger.warning("Empty webhook data received")
                return {"status": "error", "message": "Empty data"}

            # Verify signature if secret is configured
            if backend.webhook_secret:
                if not self._verify_signature(backend.webhook_secret):
                    _logger.warning(
                        "Invalid webhook signature for backend %s", backend_id
                    )
                    return {"status": "error", "message": "Invalid signature"}

            # Process webhook
            self._process_webhook(backend, data)

            return {"status": "success"}

        except Exception as e:
            _logger.exception("Error processing webhook: %s", str(e))
            return {"status": "error", "message": str(e)}

    def _verify_signature(self, secret):
        """Verify webhook signature.

        Args:
            secret: Webhook secret from backend configuration

        Returns:
            True if signature is valid
        """
        # Get signature from header
        signature = request.httprequest.headers.get("X-Trendyol-Signature")
        if not signature:
            return False

        # Calculate expected signature
        body = request.httprequest.data
        expected = hmac.new(
            secret.encode("utf-8"),
            body,
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(signature, expected)

    def _process_webhook(self, backend, data):
        """Process webhook data.

        Args:
            backend: trendyol.backend record
            data: Dict of webhook data
        """
        _logger.info(
            "Processing webhook for backend %s: %s",
            backend.id,
            json.dumps(data, indent=2, ensure_ascii=False)[:500],
        )

        # Queue processing via job
        backend.with_delay(
            channel="root.trendyol.webhook",
            description="Process Trendyol webhook",
        )._process_webhook_data(data)

    @http.route(
        "/trendyol/webhook/<int:backend_id>/test",
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
