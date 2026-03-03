# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import fields, models


class MarketplaceBrand(models.AbstractModel):
    _name = "marketplace.brand"
    _description = "Marketplace Brand"
    _order = "name"

    name = fields.Char(required=True, index=True)
    active = fields.Boolean(default=True)
