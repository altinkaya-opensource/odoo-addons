# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import fields, models


class MarketplaceCargoMapping(models.AbstractModel):
    _name = "marketplace.cargo.mapping"
    _description = "Marketplace Cargo Provider Mapping"

    provider_name = fields.Char(
        string="Provider Name",
        required=True,
        help="Cargo provider name or short code from the marketplace API",
    )
    carrier_id = fields.Many2one(
        "delivery.carrier",
        string="Delivery Carrier",
        required=True,
        help="Odoo delivery carrier to assign for this cargo provider",
    )
