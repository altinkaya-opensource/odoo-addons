# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import json
import logging

from odoo import _, api, fields, models

from .trendyol_backend import _trendyol_ts_to_utc

_logger = logging.getLogger(__name__)

TRANSACTION_TYPE_MAP = {
    "Sale": "sale",
    "Return": "return",
}


class TrendyolSettlement(models.Model):
    _name = "trendyol.settlement"
    _description = "Trendyol Settlement Transaction"
    _inherit = ["marketplace.settlement"]
    _order = "transaction_date desc, id desc"

    backend_id = fields.Many2one(
        "trendyol.backend",
        required=True,
        ondelete="cascade",
        index=True,
    )
    trendyol_settlement_id = fields.Char(
        string="Settlement ID",
        required=True,
        index=True,
    )
    shipment_package_id = fields.Char()
    barcode = fields.Char()
    description = fields.Char()

    # Financial amounts (Trendyol-specific)
    debt = fields.Float(digits=(16, 2))
    credit = fields.Float(digits=(16, 2))
    seller_revenue = fields.Float(digits=(16, 2))

    # Payment grouping
    payment_order_id = fields.Char(index=True)
    payment_date = fields.Datetime()
    receipt_id = fields.Char()

    # Odoo links
    trendyol_order_id = fields.Many2one(
        "trendyol.order",
        index=True,
    )

    _sql_constraints = [
        (
            "settlement_id_backend_uniq",
            "unique(trendyol_settlement_id, backend_id)",
            "Settlement ID must be unique per backend!",
        ),
    ]

    # ==================== Abstract Hook Implementations ====================

    def _get_marketplace_order_binding(self):
        return self.trendyol_order_id

    def _set_marketplace_order_binding(self, order):
        self.trendyol_order_id = order

    def _find_marketplace_order(self, order_number):
        return self.env["trendyol.order"].search(
            [
                ("backend_id", "=", self.backend_id.id),
                ("trendyol_order_number", "=", order_number),
            ],
            limit=1,
        )

    def _get_payment_ref(self):
        return _("Trendyol Settlement %s") % self.trendyol_settlement_id

    def _get_commission_ref(self):
        return _("Trendyol Commission - Order %s") % self.order_number

    # ==================== Import ====================

    @api.model
    def _parse_timestamp(self, timestamp):
        """Parse Trendyol timestamp (ms, GMT+3) to naive UTC datetime."""
        return _trendyol_ts_to_utc(timestamp)

    @api.model
    def _import_settlement(self, backend, data):
        """Import a single settlement from Trendyol API response.

        Args:
            backend: trendyol.backend record
            data: Dict from API response

        Returns:
            trendyol.settlement record or False
        """
        settlement_id = str(data.get("id", ""))
        if not settlement_id:
            _logger.warning("Invalid settlement data: missing ID")
            return False

        existing = self.search(
            [
                ("backend_id", "=", backend.id),
                ("trendyol_settlement_id", "=", settlement_id),
            ],
            limit=1,
        )
        if existing:
            return existing

        # Find linked trendyol.order
        order_number = data.get("orderNumber", "")
        trendyol_order = False
        if order_number:
            trendyol_order = self.env["trendyol.order"].search(
                [
                    ("backend_id", "=", backend.id),
                    ("trendyol_order_number", "=", str(order_number)),
                ],
                limit=1,
            )

        transaction_type = TRANSACTION_TYPE_MAP.get(data.get("transactionType"), "sale")

        try:
            settlement = self.create(
                {
                    "backend_id": backend.id,
                    "trendyol_settlement_id": settlement_id,
                    "transaction_type": transaction_type,
                    "transaction_date": self._parse_timestamp(
                        data.get("transactionDate")
                    ),
                    "order_number": str(order_number) if order_number else "",
                    "shipment_package_id": str(data.get("shipmentPackageId", "")),
                    "barcode": data.get("barcode", ""),
                    "description": data.get("description", ""),
                    "debt": data.get("debt", 0.0),
                    "credit": data.get("credit", 0.0),
                    "commission_rate": data.get("commissionRate", 0.0),
                    "commission_amount": data.get("commissionAmount", 0.0),
                    "seller_revenue": data.get("sellerRevenue", 0.0),
                    "payment_order_id": str(data.get("paymentOrderId", "")),
                    "payment_date": self._parse_timestamp(data.get("paymentDate")),
                    "receipt_id": str(data.get("receiptId", "")),
                    "trendyol_order_id": trendyol_order.id if trendyol_order else False,
                    "raw_data": json.dumps(data, indent=2, ensure_ascii=False),
                }
            )
            _logger.info("Imported settlement %s", settlement_id)
            return settlement

        except Exception as e:
            _logger.error("Failed to import settlement %s: %s", settlement_id, str(e))
            raise
