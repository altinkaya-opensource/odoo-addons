# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import json
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Backfill mutable API data and rebuild legacy claim lines."""
    if not version:
        return

    env = api.Environment(cr, SUPERUSER_ID, {})
    orders = env["trendyol.order"].search([("raw_data", "!=", False)])
    for order in orders:
        try:
            data = json.loads(order.raw_data)
        except (TypeError, json.JSONDecodeError):
            _logger.warning("Skipping invalid raw data on Trendyol order %s", order.id)
            continue
        vals = {}
        for api_field, odoo_field in {
            "cargoProviderName": "cargo_provider_name",
            "cargoProviderId": "cargo_provider_id",
            "cargoTrackingNumber": "cargo_tracking_number",
            "cargoTrackingLink": "cargo_tracking_link",
        }.items():
            # Creation-time raw data is stale: only fill in missing values,
            # never wipe tracking stored later by the webhook.
            value = data.get(api_field)
            if value and not order[odoo_field]:
                vals[odoo_field] = value
        if vals:
            order.write(vals)

    claims = env["trendyol.claim"].search([("raw_data", "!=", False)])
    for claim in claims:
        try:
            data = json.loads(claim.raw_data)
            with cr.savepoint():
                claim._import_claim(claim.backend_id, data)
        except Exception:
            _logger.exception("Could not rebuild Trendyol claim %s", claim.id)

    settlements = env["trendyol.settlement"].search(
        [
            "|",
            ("payment_order_id", "=", "None"),
            ("receipt_id", "=", "None"),
        ]
    )
    for settlement in settlements:
        settlement.write(
            {
                "payment_order_id": False
                if settlement.payment_order_id == "None"
                else settlement.payment_order_id,
                "receipt_id": False
                if settlement.receipt_id == "None"
                else settlement.receipt_id,
            }
        )
