# Copyright 2025 Altinkaya Enclosures
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import fields, models


class TrendyolCargoMapping(models.Model):
    _name = "trendyol.cargo.mapping"
    _description = "Trendyol Cargo Provider Mapping"

    backend_id = fields.Many2one(
        "trendyol.backend",
        string="Backend",
        required=True,
        ondelete="cascade",
    )
    trendyol_cargo_provider_name = fields.Char(
        required=True,
        help="Cargo provider name from Trendyol API (cargoProviderName)",
    )
    carrier_id = fields.Many2one(
        "delivery.carrier",
        string="Delivery Carrier",
        required=True,
        help="Odoo delivery carrier to assign for this Trendyol cargo provider",
    )
