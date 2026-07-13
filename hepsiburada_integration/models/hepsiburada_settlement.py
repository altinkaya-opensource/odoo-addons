# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import json
import logging

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)

TRANSACTION_TYPE_MAP = {
    "Payment": "sale",
    "Return": "return",
    "Commission": "commission",
}


class HepsiburadaSettlement(models.Model):
    _name = "hepsiburada.settlement"
    _description = "Hepsiburada Settlement Transaction"
    _order = "transaction_date desc, id desc"
    _inherit = ["marketplace.settlement.mixin", "mail.thread"]

    backend_id = fields.Many2one(
        "hepsiburada.backend",
        required=True,
        ondelete="cascade",
        index=True,
    )
    hb_transaction_id = fields.Char(
        string="Transaction ID",
        index=True,
    )
    transaction_type = fields.Selection(
        [
            ("sale", "Sale"),
            ("return", "Return"),
            ("commission", "Commission"),
        ],
        required=True,
        index=True,
    )
    transaction_date = fields.Datetime(index=True)
    order_number = fields.Char(index=True)
    package_number = fields.Char()
    sku = fields.Char()
    description = fields.Char()

    # Financial amounts
    amount = fields.Float(digits=(16, 2))
    commission_rate = fields.Float(digits=(6, 2))
    commission_amount = fields.Float(digits=(16, 2))
    currency_code = fields.Char(help="949=TRY, 840=USD")

    # Payment info
    payment_date = fields.Datetime()
    payment_status = fields.Char(help="Paid / WillBePaid")
    invoice_number = fields.Char()

    # Odoo links
    hb_order_id = fields.Many2one(
        "hepsiburada.order",
        index=True,
    )
    odoo_invoice_id = fields.Many2one(
        "account.move",
        string="Invoice",
    )
    odoo_payment_id = fields.Many2one(
        "account.payment",
        string="Payment",
    )
    commission_payment_id = fields.Many2one(
        "account.payment",
    )

    # Status
    state = fields.Selection(
        [
            ("imported", "Imported"),
            ("reconciled", "Reconciled"),
            ("error", "Error"),
        ],
        default="imported",
        required=True,
        index=True,
        tracking=True,
    )
    error_message = fields.Text()
    raw_data = fields.Text()

    _sql_constraints = [
        (
            "transaction_uniq",
            "unique(hb_transaction_id, backend_id)",
            "Transaction ID must be unique per backend!",
        ),
    ]

    @staticmethod
    def _numeric_value(value):
        """Extract a scalar from Hepsiburada's nested money objects."""
        if isinstance(value, dict):
            value = value.get("value", value.get("amount", 0.0))
        return value or 0.0

    @api.model
    def _import_settlement(self, backend, data):
        """Import a single settlement from Hepsiburada API response.

        Args:
            backend: hepsiburada.backend record
            data: Dict from API response

        Returns:
            hepsiburada.settlement record or False
        """
        transaction_id = str(data.get("id", ""))

        # Check for duplicate
        if transaction_id:
            existing = self.search(
                [
                    ("backend_id", "=", backend.id),
                    ("hb_transaction_id", "=", transaction_id),
                ],
                limit=1,
            )
            if existing:
                return existing

        # Find linked hepsiburada.order
        order_number = str(data.get("orderNumber", ""))
        hb_order = False
        if order_number:
            hb_order = self.env["hepsiburada.order"].search(
                [
                    ("backend_id", "=", backend.id),
                    ("hb_order_number", "=", order_number),
                ],
                limit=1,
            )

        transaction_type = TRANSACTION_TYPE_MAP.get(
            data.get("transactionType", ""), "sale"
        )
        amount_data = data.get("amount", 0.0)
        currency_code = data.get("currencyCode")
        if isinstance(amount_data, dict):
            currency_code = amount_data.get("currencyCode") or currency_code

        try:
            settlement = self.create(
                {
                    "backend_id": backend.id,
                    "hb_transaction_id": transaction_id,
                    "transaction_type": transaction_type,
                    "transaction_date": data.get("recordDate"),
                    "order_number": order_number,
                    "package_number": str(data.get("packageNumber", "")),
                    "sku": data.get("sku", ""),
                    "description": data.get("description", ""),
                    "amount": self._numeric_value(amount_data),
                    "commission_rate": self._numeric_value(
                        data.get("commissionRate", 0.0)
                    ),
                    "commission_amount": self._numeric_value(
                        data.get("commissionAmount", 0.0)
                    ),
                    "currency_code": str(currency_code or "949"),
                    "payment_date": data.get("paymentDate"),
                    "payment_status": data.get("status", ""),
                    "invoice_number": data.get("invoiceNumber", ""),
                    "hb_order_id": hb_order.id if hb_order else False,
                    "raw_data": json.dumps(data, indent=2, ensure_ascii=False),
                }
            )
            _logger.info("Imported HB settlement %s", transaction_id)
            return settlement

        except Exception:
            _logger.error(
                "Failed to import HB settlement %s",
                transaction_id,
                exc_info=True,
            )
            raise

    def _marketplace_name(self):
        return _("Hepsiburada")

    def _marketplace_order_model(self):
        return "hepsiburada.order"

    def _marketplace_order_number_field(self):
        return "hb_order_number"

    def _marketplace_order_link_field(self):
        return "hb_order_id"

    def _marketplace_partner_field(self):
        return "hb_partner_id"

    def _marketplace_payment_ref(self):
        return _("HB Settlement - Order %s") % self.order_number

    def _marketplace_commission_ref(self):
        return _("HB Commission - Order %s") % self.order_number

    def _marketplace_commission_amount(self):
        commission_amt = super()._marketplace_commission_amount()
        if not commission_amt and self.transaction_type == "commission":
            commission_amt = abs(self.amount)
        return commission_amt
