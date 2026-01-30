"""
Created on Jul 18, 2016

@author: Codequarters_ugur
"""

from odoo import api, fields, models


class product_product(models.Model):
    _inherit = "product.product"

    route_ids = fields.Many2many(
        "stock.route",
        string="Routes",
        domain="[('product_selectable', '=', True)]",
        compute="_compute_variant_routes",
        store=True,
    )

    variant_route_ids = fields.Many2many(
        "stock.route",
        "stock_route_product_variant",
        "product_id",
        "route_id",
        string="Variant Routes",
    )

    @api.depends("variant_route_ids", "product_tmpl_id", "product_tmpl_id.route_ids")
    def _compute_variant_routes(self):
        for product in self:
            if product.variant_route_ids:
                product.route_ids = product.variant_route_ids
            else:
                product.route_ids = product.product_tmpl_id.route_ids
