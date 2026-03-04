# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import models


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    def _compute_price_unit(self):
        """Skip pricelist computation for marketplace order lines.

        Marketplace prices come from the marketplace API and must not
        be overwritten by the Odoo pricelist engine.
        """
        marketplace_lines = self.filtered(lambda l: l.order_id.is_marketplace_order)
        return super(SaleOrderLine, self - marketplace_lines)._compute_price_unit()

    def explode_set_contents(self):
        """Distribute marketplace pack prices across exploded component lines.

        When a phantom BoM line from a marketplace order is exploded, the
        original line (with the API price) is deleted and component lines
        are created.  We capture each pack line's net subtotal before the
        explosion, then distribute it proportionally (by cost) to the
        resulting component lines so the order total stays correct.

        Note: ``set_product`` and ``set_parent_product_id`` come from the
        ``altinkaya_sales`` / ``website_set_product`` modules.  A
        ``getattr`` guard is used so this override is harmless when those
        modules are not installed.
        """
        marketplace_set_lines = self.filtered(
            lambda l: (
                l.order_id.is_marketplace_order
                and getattr(l, "set_product", False)
                and l.state in ("draft", "sent")
            )
        )

        # Save net subtotals and tax_ids before super() unlinks these lines
        price_map = {}
        for line in marketplace_set_lines:
            subtotal = (
                line.price_unit * line.product_uom_qty * (1 - line.discount / 100)
            )
            price_map[(line.order_id.id, line.product_id.id)] = {
                "subtotal": subtotal,
                "tax_ids": line.tax_id.ids,
            }

        parent = super()
        parent_method = getattr(parent, "explode_set_contents", None)
        if parent_method is None:
            return
        result = parent_method()

        if not price_map:
            return result

        # Distribute saved subtotals and tax_ids to the new component lines
        for (order_id, parent_product_id), line_data in price_map.items():
            order = self.env["sale.order"].browse(order_id)
            component_lines = order.order_line.filtered(
                lambda l, pid=parent_product_id: l.set_parent_product_id.id == pid
            )
            if not component_lines:
                continue

            original_subtotal = line_data["subtotal"]
            total_cost = sum(
                l.product_id.standard_price * l.product_uom_qty for l in component_lines
            )

            for cl in component_lines:
                cl.tax_id = [(6, 0, line_data["tax_ids"])]
                if total_cost and cl.product_uom_qty:
                    proportion = (
                        cl.product_id.standard_price * cl.product_uom_qty
                    ) / total_cost
                    cl.price_unit = (
                        original_subtotal * proportion
                    ) / cl.product_uom_qty
                elif cl.product_uom_qty:
                    # Equal distribution fallback when costs are zero
                    total_qty = sum(l.product_uom_qty for l in component_lines)
                    cl.price_unit = original_subtotal / total_qty

        return result
