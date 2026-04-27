# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import api, fields, models


class HepsiburadaBrand(models.Model):
    _name = "hepsiburada.brand"
    _description = "Hepsiburada Brand"
    _inherit = ["marketplace.brand.mixin"]

    backend_id = fields.Many2one(
        "hepsiburada.backend",
        required=True,
        ondelete="cascade",
        index=True,
    )

    _sql_constraints = [
        (
            "name_backend_uniq",
            "unique(name, backend_id)",
            "Brand name must be unique per backend!",
        ),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("external_id") and vals.get("name"):
                vals["external_id"] = vals["name"]
        return super().create(vals_list)
