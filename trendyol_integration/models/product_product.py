# Copyright 2025 Altinkaya Enclosures
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
        string="Trendyol Binding Count",
        compute="_compute_trendyol_binding_count",
    )
    image_url = fields.Char(
        string="Image URL",
        help="Public HTTPS URL for product image (used for marketplace integrations)",
    )

    def _compute_trendyol_binding_count(self):
        for product in self:
            product.trendyol_binding_count = len(product.trendyol_binding_ids)

    def action_view_trendyol_bindings(self):
        """View Trendyol bindings for this product."""
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
        string="Trendyol Binding Count",
        compute="_compute_trendyol_binding_count",
    )

    def _compute_trendyol_binding_count(self):
        for template in self:
            template.trendyol_binding_count = sum(
                template.product_variant_ids.mapped("trendyol_binding_count")
            )

    def action_view_trendyol_bindings(self):
        """View Trendyol bindings for all variants."""
        self.ensure_one()
        product_ids = self.product_variant_ids.ids
        return {
            "type": "ir.actions.act_window",
            "name": "Trendyol Bindings",
            "res_model": "trendyol.product.binding",
            "view_mode": "tree,form",
            "domain": [("odoo_id", "in", product_ids)],
        }
