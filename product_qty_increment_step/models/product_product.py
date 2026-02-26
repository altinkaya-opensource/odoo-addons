# Copyright 2023 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo import fields, models


class ProductProduct(models.Model):
    _inherit = "product.product"

    min_order_qty = fields.Integer(
        default=0,
        help="Minimum order quantity for this product in the webshop."
        " Set 0 to disable this feature.",
    )
