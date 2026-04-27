# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import models


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    def _is_marketplace_api_priced_line(self):
        return self.order_id._is_marketplace_order()

    def _marketplace_set_content_subtotal(self):
        """Return the marketplace line subtotal before set explosion."""
        self.ensure_one()
        discount = (self.discount or 0.0) / 100
        return self.price_unit * self.product_uom_qty * (1 - discount)

    def _compute_price_unit(self):
        """Keep marketplace API prices instead of recomputing from pricelists."""
        marketplace_lines = self.filtered(
            lambda line: line._is_marketplace_api_priced_line()
        )
        return super(SaleOrderLine, self - marketplace_lines)._compute_price_unit()

    def explode_set_contents(self):
        """Distribute marketplace set prices across exploded component lines."""
        marketplace_set_lines = self.filtered(
            lambda line: (
                line._is_marketplace_api_priced_line()
                and line.set_product
                and line.state in ("draft", "sent")
            )
        )

        price_map = {}
        for line in marketplace_set_lines:
            key = (line.order_id.id, line.product_id.id)
            line_data = price_map.setdefault(
                key,
                {
                    "subtotal": 0.0,
                    "tax_ids": line.tax_id.ids,
                },
            )
            line_data["subtotal"] += line._marketplace_set_content_subtotal()

        result = super().explode_set_contents()

        for (order_id, parent_product_id), line_data in price_map.items():
            order = self.env["sale.order"].browse(order_id)
            component_lines = order.order_line.filtered(
                lambda line, pid=parent_product_id: line.set_parent_product_id.id == pid
            )
            if not component_lines:
                continue

            original_subtotal = line_data["subtotal"]
            total_cost = sum(
                line.product_id.standard_price * line.product_uom_qty
                for line in component_lines
            )
            total_qty = sum(line.product_uom_qty for line in component_lines)

            for component_line in component_lines:
                component_line.tax_id = [(6, 0, line_data["tax_ids"])]
                if total_cost and component_line.product_uom_qty:
                    proportion = (
                        component_line.product_id.standard_price
                        * component_line.product_uom_qty
                    ) / total_cost
                    component_line.price_unit = (
                        original_subtotal * proportion
                    ) / component_line.product_uom_qty
                    component_line.discount = 0.0
                elif total_qty and component_line.product_uom_qty:
                    component_line.price_unit = original_subtotal / total_qty
                    component_line.discount = 0.0

        return result
