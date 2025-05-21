# Copyright 2024 Ahmet Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo import fields, models


class PurchaseRequisition(models.Model):
    _inherit = "purchase.requisition"

    account_move_id = fields.Many2one(
        "account.move",
        string="Invoice",
    )
