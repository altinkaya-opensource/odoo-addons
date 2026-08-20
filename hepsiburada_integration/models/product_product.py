# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import fields, models


class ProductProduct(models.Model):
    _inherit = "product.product"

    hepsiburada_binding_ids = fields.One2many(
        "hepsiburada.product.binding",
        "odoo_id",
        string="Hepsiburada Bindings",
    )
    hepsiburada_binding_count = fields.Integer(
        compute="_compute_hepsiburada_binding_count",
    )
    is_published_hepsiburada = fields.Boolean(
        string="Published on Hepsiburada",
        default=lambda self: (
            self.product_tmpl_id.is_published_hepsiburada
            if self.product_tmpl_id
            else False
        ),
        help="Variant is eligible for export to Hepsiburada",
    )

    def _compute_hepsiburada_binding_count(self):
        for product in self:
            product.hepsiburada_binding_count = len(product.hepsiburada_binding_ids)

    def action_view_hepsiburada_bindings(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Hepsiburada Bindings",
            "res_model": "hepsiburada.product.binding",
            "view_mode": "tree,form",
            "domain": [("odoo_id", "=", self.id)],
            "context": {"default_odoo_id": self.id},
        }
