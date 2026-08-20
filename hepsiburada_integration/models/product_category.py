# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import fields, models


class ProductCategory(models.Model):
    _inherit = "product.category"

    is_published_hepsiburada = fields.Boolean(
        string="Published on Hepsiburada",
        default=False,
        help="Category is eligible for Hepsiburada export. Products are filtered "
        "to require both `is_published_hepsiburada` on the product and on the "
        "category.",
    )
