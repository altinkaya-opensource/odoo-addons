# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    is_marketplace_order = fields.Boolean(
        string="Marketplace Order",
        default=False,
        readonly=True,
        copy=False,
        help="Set automatically when this order is created "
        "from a marketplace integration.",
    )
