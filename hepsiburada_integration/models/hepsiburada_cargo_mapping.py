# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import fields, models


class HepsiburadaCargoMapping(models.Model):
    _name = "hepsiburada.cargo.mapping"
    _description = "Hepsiburada Cargo Provider Mapping"

    backend_id = fields.Many2one(
        "hepsiburada.backend",
        required=True,
        ondelete="cascade",
    )
    hepsiburada_cargo_provider_name = fields.Char(
        required=True,
        help="Cargo provider name from Hepsiburada API",
    )
    carrier_id = fields.Many2one(
        "delivery.carrier",
        string="Delivery Carrier",
        help="Odoo delivery carrier to assign for this cargo provider",
    )
