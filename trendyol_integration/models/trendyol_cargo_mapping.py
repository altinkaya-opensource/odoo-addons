# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import fields, models


class TrendyolCargoMapping(models.Model):
    _name = "trendyol.cargo.mapping"
    _description = "Trendyol Cargo Provider Mapping"
    _inherit = ["marketplace.cargo.mapping"]

    backend_id = fields.Many2one(
        "trendyol.backend",
        required=True,
        ondelete="cascade",
    )
