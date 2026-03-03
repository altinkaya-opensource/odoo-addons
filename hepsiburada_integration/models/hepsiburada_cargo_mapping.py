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
    hb_cargo_short_name = fields.Char(
        string="Cargo Short Name",
        required=True,
        help="Cargo provider short name from Hepsiburada API "
        "(e.g. 'HX' for HepsiJet, 'AK' for Aras)",
    )
    carrier_id = fields.Many2one(
        "delivery.carrier",
        string="Delivery Carrier",
        required=True,
        help="Odoo delivery carrier to assign for this Hepsiburada cargo provider",
    )
