# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import fields, models


class ProductProduct(models.Model):
    _inherit = "product.product"

    trendyol_binding_ids = fields.One2many(
        "trendyol.product.binding",
        "odoo_id",
        string="Trendyol Bindings",
    )
    trendyol_binding_count = fields.Integer(
        compute="_compute_trendyol_binding_count",
    )
    is_published_trendyol = fields.Boolean(
        string="Published on Trendyol",
        default=lambda self: (
            self.product_tmpl_id.is_published_trendyol
            if self.product_tmpl_id
            else False
        ),
        help="Variant is eligible for export to Trendyol",
    )

    def _compute_trendyol_binding_count(self):
        for product in self:
            product.trendyol_binding_count = len(product.trendyol_binding_ids)

    def action_view_trendyol_bindings(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Trendyol Bindings",
            "res_model": "trendyol.product.binding",
            "view_mode": "tree,form",
            "domain": [("odoo_id", "=", self.id)],
            "context": {"default_odoo_id": self.id},
        }


class ProductTemplate(models.Model):
    _inherit = "product.template"

    trendyol_binding_count = fields.Integer(
        compute="_compute_trendyol_binding_count",
    )
    is_published_trendyol = fields.Boolean(
        string="Published on Trendyol",
        default=False,
        help="Template is eligible for export to Trendyol",
    )

    def _compute_trendyol_binding_count(self):
        for template in self:
            template.trendyol_binding_count = sum(
                template.product_variant_ids.mapped("trendyol_binding_count")
            )

    def action_view_trendyol_bindings(self):
        self.ensure_one()
        product_ids = self.product_variant_ids.ids
        return {
            "type": "ir.actions.act_window",
            "name": "Trendyol Bindings",
            "res_model": "trendyol.product.binding",
            "view_mode": "tree,form",
            "domain": [("odoo_id", "in", product_ids)],
        }
