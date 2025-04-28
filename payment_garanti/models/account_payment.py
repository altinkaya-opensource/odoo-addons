# Copyright 2025 Ahmet Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo import api, fields, models


class AccountPayment(models.Model):
    _inherit = "account.payment"

    sanalpos_payment = fields.Boolean(
        string="SanalPOS Payment",
        help="This payment is made through Garanti Sanal Pos",
        readonly=True,
        copy=False,
        store=True,
        compute="_compute_sanalpos_payment",
    )

    @api.depends("payment_transaction_id")
    def _compute_sanalpos_payment(self):
        for rec in self:
            rec.sanalpos_payment = bool(
                rec.payment_transaction_id.garanti_secure3d_hash
            )
