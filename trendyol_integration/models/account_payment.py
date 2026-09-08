# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import api, fields, models


class AccountPayment(models.Model):
    _inherit = "account.payment"

    trendyol_commission_settlement_ids = fields.One2many(
        "trendyol.settlement", "commission_payment_id"
    )
    is_trendyol_commission = fields.Boolean(
        compute="_compute_is_trendyol_commission", store=True, index=True
    )

    @api.depends("trendyol_commission_settlement_ids")
    def _compute_is_trendyol_commission(self):
        """Identify current and legacy commission payments by their actual links."""
        for payment in self:
            payment.is_trendyol_commission = bool(
                payment.trendyol_commission_settlement_ids
            )
