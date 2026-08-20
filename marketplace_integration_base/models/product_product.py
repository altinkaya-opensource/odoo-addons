# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import fields, models


class ProductProduct(models.Model):
    _inherit = "product.product"

    image_url = fields.Char(
        string="Marketplace Image URL",
        help="Public HTTPS URL for the main product image. Used by marketplace "
        "integrations as the first image when no base_multi_image records "
        "expose a published URL.",
    )
