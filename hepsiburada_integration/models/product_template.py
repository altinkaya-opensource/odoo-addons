# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    hepsiburada_binding_count = fields.Integer(
        compute="_compute_hepsiburada_binding_count",
    )
    is_published_hepsiburada = fields.Boolean(
        string="Published on Hepsiburada",
        default=False,
        help="Template is eligible for export to Hepsiburada",
    )

    def _compute_hepsiburada_binding_count(self):
        for template in self:
            template.hepsiburada_binding_count = sum(
                template.product_variant_ids.mapped("hepsiburada_binding_count")
            )

    def action_view_hepsiburada_bindings(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Hepsiburada Bindings",
            "res_model": "hepsiburada.product.binding",
            "view_mode": "tree,form",
            "domain": [("odoo_id", "in", self.product_variant_ids.ids)],
        }
