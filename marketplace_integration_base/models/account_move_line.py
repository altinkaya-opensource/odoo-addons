# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import api, models


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    @api.model_create_multi
    def create(self, vals_list):
        """Inherit tax_ids from the sale order line for marketplace orders.

        Invoices for marketplace orders are created from pickings via
        stock_picking_invoicing, which recomputes the tax from the product's
        default (price-excluded) tax instead of the sale order line's tax.
        Marketplace lines use a price-included tax (e.g. KDV %10 Dahil), so
        the recompute mismatches the order and inflates the invoice total.
        Restore the sale order line's tax on those invoice lines.
        """
        lines = super().create(vals_list)
        for line in lines:
            sale_lines = line.move_line_ids.mapped("sale_line_id")
            if not sale_lines:
                continue
            marketplace_lines = sale_lines.filtered(
                lambda l: l.order_id._is_marketplace_order()
            )
            if not marketplace_lines:
                continue
            line.tax_ids = marketplace_lines.tax_id
        return lines
