# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import models


class ProductProduct(models.Model):
    _inherit = "product.product"
    # Future: hb_binding_ids for product listing management
