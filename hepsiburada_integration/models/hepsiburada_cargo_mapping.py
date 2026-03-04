# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import fields, models


class HepsiburadaCargoMapping(models.Model):
    _name = "hepsiburada.cargo.mapping"
    _description = "Hepsiburada Cargo Provider Mapping"
    _inherit = ["marketplace.cargo.mapping"]

    backend_id = fields.Many2one(
        "hepsiburada.backend",
        required=True,
        ondelete="cascade",
    )
