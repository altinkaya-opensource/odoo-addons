# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import fields, models


class MarketplaceBrandMixin(models.AbstractModel):
    """Abstract mixin for marketplace brand catalogs.

    Concrete child models declare _name, _inherit, and `backend_id`.
    """

    _name = "marketplace.brand.mixin"
    _description = "Marketplace Brand Mixin"
    _order = "name"

    name = fields.Char(required=True, index=True)
    external_id = fields.Char(
        string="External ID",
        required=True,
        index=True,
        help="Identifier of this brand in the marketplace",
    )
