# Copyright 2023 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo import fields, models


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    set_product = fields.Boolean(
        "Set product?", related="product_id.product_tmpl_id.set_product"
    )
    set_parent_product_id = fields.Many2one(
        comodel_name="product.product",
        string="Parent Product",
        readonly=True,
    )

    # @api.depends("product_id")
    # def _compute_set_product(self):
    #     bom_obj = self.env["mrp.bom"].sudo()
    #     bom_dict = bom_obj._bom_find(products=self.product_id)
    #     if not bom_dict:
    #         self.set_product = False
    #     if not bom_dict.get(self.product_id, False):
    #         self.set_product = False
    #     else:
    #         self.set_product = bom_dict[self.product_id].type == "phantom"

    def explode_set_contents(self):
        """Explodes order lines."""
        self = self.with_context(exploding_set_contents=True)
        bom_obj = self.env["mrp.bom"].sudo()
        to_unlink_ids = self.env["sale.order.line"]
        to_explode_again_ids = self.env["sale.order.line"]

        for line in self.filtered(
            lambda ln: ln.set_product and ln.state in ["draft", "sent"]
        ):
            # Avoid using self in this loop, we are passing context to lines
            if not (parent_id := line._context.get("set_parent_product_id", False)):
                line = line.with_context(set_parent_product_id=line.product_id.id)
                parent_id = line.product_id.id

            bom_dict = bom_obj._bom_find(products=line.product_id)
            customer_lang = line.order_id.partner_id.lang
            if not bom_dict:
                continue
            if not bom_dict.get(line.product_id, False):
                continue

            bom_id = bom_dict[line.product_id]
            # bom_id = bom_obj.browse(bom_id)
            if bom_id.type == "phantom":
                factor = (
                    line.product_uom._compute_quantity(
                        line.product_qty, bom_id.product_uom_id
                    )
                    / bom_id.product_qty
                )
                boms, lines = bom_id.explode(
                    line.product_id, factor, picking_type=bom_id.picking_type_id
                )

                for _bom_line, data in lines:
                    product = data["target_product"]
                    sol = line.env["sale.order.line"].new()
                    sol.order_id = line.order_id
                    sol.product_id = product
                    sol.set_parent_product_id = parent_id
                    sol.product_uom_qty = data["qty"]  # data['qty']
                    # sol.product_id_change()
                    # sol.product_uom_change()
                    # sol._onchange_discount()
                    # sol._compute_amount()
                    sol.name = product.with_context(lang=customer_lang).display_name
                    vals = sol._convert_to_write(sol._cache)
                    existing_sol = sol.order_id.order_line.filtered(
                        lambda ln, sol=sol, parent_id=parent_id: (
                            ln.id
                            and ln.product_id == sol.product_id
                            and ln.set_parent_product_id.id == parent_id
                        )
                    )
                    if existing_sol:
                        existing_sol.write(
                            {
                                "product_uom_qty": existing_sol.product_uom_qty
                                + data["qty"]
                            }
                        )
                    else:
                        sol_id = line.create(vals)
                        to_explode_again_ids |= sol_id
                to_unlink_ids |= line

        # check if new moves needs to be exploded
        if to_explode_again_ids:
            to_explode_again_ids.explode_set_contents()
        # delete the line with original product which is not relevant anymore
        if to_unlink_ids:
            to_unlink_ids.unlink()

        return fields.first(to_explode_again_ids)
