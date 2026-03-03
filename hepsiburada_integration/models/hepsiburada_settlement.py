# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import json
import logging
from datetime import datetime, timezone

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)

TRANSACTION_TYPE_MAP = {
    "Sale": "sale",
    "Return": "return",
}


class HepsiburadaSettlement(models.Model):
    _name = "hepsiburada.settlement"
    _inherit = "marketplace.settlement"
    _description = "Hepsiburada Settlement Transaction"

    backend_id = fields.Many2one(
        "hepsiburada.backend",
        required=True,
        ondelete="cascade",
        index=True,
    )
    hb_settlement_id = fields.Char(
        string="Settlement ID",
        required=True,
        index=True,
    )

    # Odoo links
    hb_order_id = fields.Many2one(
        "hepsiburada.order",
        index=True,
    )

    _sql_constraints = [
        (
            "settlement_id_backend_uniq",
            "unique(hb_settlement_id, backend_id)",
            "Settlement ID must be unique per backend!",
        ),
    ]

    @api.model
    def _parse_timestamp(self, timestamp):
        """Parse Hepsiburada timestamp to naive UTC datetime."""
        if not timestamp:
            return False
        try:
            if isinstance(timestamp, (int, float)):
                return datetime.fromtimestamp(
                    timestamp / 1000, tz=timezone.utc
                ).replace(tzinfo=None)
            return fields.Datetime.from_string(timestamp)
        except (ValueError, TypeError, OSError):
            return False

    @api.model
    def _import_settlement(self, backend, data):
        """Import a single settlement from Hepsiburada API response.

        Args:
            backend: hepsiburada.backend record
            data: Dict from API response

        Returns:
            hepsiburada.settlement record or False
        """
        settlement_id = str(data.get("id", ""))
        if not settlement_id:
            _logger.warning("Invalid HB settlement data: missing ID")
            return False

        existing = self.search(
            [
                ("backend_id", "=", backend.id),
                ("hb_settlement_id", "=", settlement_id),
            ],
            limit=1,
        )
        if existing:
            return existing

        order_number = data.get("orderNumber", "")
        hb_order = False
        if order_number:
            hb_order = self.env["hepsiburada.order"].search(
                [
                    ("backend_id", "=", backend.id),
                    ("hb_order_number", "=", str(order_number)),
                ],
                limit=1,
            )

        transaction_type = TRANSACTION_TYPE_MAP.get(
            data.get("transactionType"), "sale"
        )

        try:
            settlement = self.create(
                {
                    "backend_id": backend.id,
                    "hb_settlement_id": settlement_id,
                    "transaction_type": transaction_type,
                    "transaction_date": self._parse_timestamp(
                        data.get("transactionDate")
                    ),
                    "order_number": str(order_number) if order_number else "",
                    "barcode": data.get("barcode", ""),
                    "description": data.get("description", ""),
                    "debt": data.get("debt", 0.0),
                    "credit": data.get("credit", 0.0),
                    "commission_rate": data.get("commissionRate", 0.0),
                    "commission_amount": data.get("commissionAmount", 0.0),
                    "seller_revenue": data.get("sellerRevenue", 0.0),
                    "payment_order_id": str(data.get("paymentOrderId", "")),
                    "payment_date": self._parse_timestamp(data.get("paymentDate")),
                    "hb_order_id": hb_order.id if hb_order else False,
                    "raw_data": json.dumps(data, indent=2, ensure_ascii=False),
                }
            )
            _logger.info("Imported HB settlement %s", settlement_id)
            return settlement

        except Exception as e:
            _logger.error(
                "Failed to import HB settlement %s: %s", settlement_id, str(e)
            )
            raise

    def _get_settlement_id(self):
        return self.hb_settlement_id

    def _reconcile(self):
        """Find invoice, create payment + commission JE, reconcile."""
        self.ensure_one()
        backend = self.backend_id

        if not backend.settlement_journal_id:
            self.write(
                {
                    "state": "error",
                    "error_message": _(
                        "Hepsiburada Payment Journal not configured on backend."
                    ),
                }
            )
            return

        hb_order = self.hb_order_id
        if not hb_order and self.order_number:
            hb_order = self.env["hepsiburada.order"].search(
                [
                    ("backend_id", "=", backend.id),
                    ("hb_order_number", "=", self.order_number),
                ],
                limit=1,
            )
            if hb_order:
                self.hb_order_id = hb_order

        if not hb_order:
            self.write(
                {
                    "state": "error",
                    "error_message": _(
                        "Hepsiburada order not found for order number: %s"
                    )
                    % self.order_number,
                }
            )
            return

        sale_order = hb_order.odoo_id
        if not sale_order:
            self.write(
                {
                    "state": "error",
                    "error_message": _("No linked Odoo sale order found."),
                }
            )
            return

        if self.transaction_type == "sale":
            self._reconcile_sale(sale_order)
        elif self.transaction_type == "return":
            self._reconcile_return(sale_order)
