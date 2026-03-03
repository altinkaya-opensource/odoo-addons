# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import fields, models


class ProductProduct(models.Model):
    _inherit = "product.product"

    image_url = fields.Char(
        string="Image URL",
        help="Public HTTPS URL for product image (used for marketplace integrations)",
    )
