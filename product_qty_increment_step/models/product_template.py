# Copyright 2023 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    qty_increment_step = fields.Integer(
        default=1,
        help="Set a step for product quantity increment in the product page."
        " Set 0 to disable this feature.",
    )
    min_order_qty = fields.Integer(
        default=0,
        help="Minimum order quantity for this product in the webshop."
        " Set 0 to disable this feature.",
    )
