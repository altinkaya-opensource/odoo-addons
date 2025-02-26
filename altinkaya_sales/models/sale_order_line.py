# Copyright (C) 2025 Ahmet Yiğit Budak (https://github.com/yibudak)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
from odoo import api, fields, models


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    show_custom_products = fields.Boolean("Show Custom Products")
    set_product = fields.Boolean("Set product?", compute="_compute_set_product")
    date_order = fields.Datetime(related="order_id.date_order")
    set_parent_product_id = fields.Many2one(
        comodel_name="product.product",
        string="Parent Product",
        readonly=True,
    )

    def copy_line_to_active_order(self):
        sale = self.env["sale.order"].browse(
            self.env.context.get("active_order_id")
            or self.env.context.get("params", {}).get("id")
        )
        for line in self:
            sale.write(
                {
                    "order_line": [
                        (
                            0,
                            0,
                            {
                                "name": line.name,
                                "product_id": line.product_id.id,
                                "product_uom_qty": line.product_uom_qty,
                            },
                        )
                    ]
                }
            )

            sale.order_line._compute_amount()

    @api.depends("product_id")
    def _compute_set_product(self):
        bom_obj = self.env["mrp.bom"].sudo()
        bom_dict = bom_obj._bom_find(products=self.product_id)
        if not bom_dict:
            self.set_product = False
        else:
            # bom_id = bom_obj.browse(bom_id.id)
            bom_id = bom_dict[self.product_id]
            self.set_product = bom_id.type == "phantom"

    @api.onchange("show_custom_products")
    def onchange_show_custom(self):
        domain = [("sale_ok", "=", True)]
        self.product_tmpl_id = False
        self.product_id = False

        if not self.show_custom_products:
            custom_categories = self.env["product.category"].search(
                [("custom_products", "=", True)]
            )
            domain = [
                "&",
                ("sale_ok", "=", True),
                ("categ_id", "not in", custom_categories.ids),
            ]

        return {"domain": {"product_tmpl_id": domain}}

    def explode_set_contents(self):
        """Explodes order lines."""
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
                        lambda ln, sol=sol, parent_id=parent_id: ln.id
                        and ln.product_id == sol.product_id
                        and ln.set_parent_product_id.id == parent_id
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
