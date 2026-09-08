# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import api, fields, models


class AccountPayment(models.Model):
    _inherit = "account.payment"

    hepsiburada_commission_settlement_ids = fields.One2many(
        "hepsiburada.settlement", "commission_payment_id"
    )
    is_hepsiburada_commission = fields.Boolean(
        compute="_compute_is_hepsiburada_commission", store=True, index=True
    )

    @api.depends("hepsiburada_commission_settlement_ids")
    def _compute_is_hepsiburada_commission(self):
        """Reserve current and historical commission payments by actual links."""
        for payment in self:
            payment.is_hepsiburada_commission = bool(
                payment.hepsiburada_commission_settlement_ids
            )
