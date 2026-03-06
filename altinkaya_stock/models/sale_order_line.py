from collections import defaultdict

from odoo import api, fields, models
from odoo.tools import float_is_zero, float_round


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    qty_unreserved_sincan = fields.Float(
        "Sincan Depo Mevcut", related="product_id.qty_unreserved_sincan"
    )
    qty_unreserved_merkez = fields.Float(
        "Merkez Depo Mevcut", related="product_id.qty_unreserved_merkez"
    )
    producible_qty = fields.Float(
        "Üretilebilir Miktar",
        compute="_compute_producible_qty",
        digits="Product Unit of Measure",
    )

    @api.depends("product_id")
    def _compute_producible_qty(self):
        bom_obj = self.env["mrp.bom"].sudo()
        products = self.filtered(
            lambda l: l.product_id and l.product_id.type == "product"
        ).mapped("product_id")
        bom_dict = bom_obj._bom_find(products=products) if products else {}

        for line in self:
            line.producible_qty = 0.0
            product = line.product_id
            if not product or product.type != "product":
                continue

            bom = bom_dict.get(product)
            if not bom or bom.type == "phantom":
                continue

            _boms_done, lines_done = bom.explode(product, 1.0)

            # Aggregate component quantities (same product can appear multiple times)
            components_qty_needed = defaultdict(float)
            for _bom_line, data in lines_done:
                comp_product = data["target_product"]
                if comp_product.type != "product":
                    continue
                qty = data["qty"]
                if float_is_zero(qty, precision_rounding=comp_product.uom_id.rounding):
                    continue
                components_qty_needed[comp_product.id] += qty

            if not components_qty_needed:
                continue

            # Calculate producible quantity
            producibles = []
            for comp_id, qty_needed in components_qty_needed.items():
                comp = self.env["product.product"].browse(comp_id)
                free = comp.free_qty
                producibles.append(
                    float_round(
                        free / qty_needed,
                        precision_digits=0,
                        rounding_method="DOWN",
                    )
                )

            if producibles:
                line.producible_qty = max(0, min(producibles) * bom.product_qty)
