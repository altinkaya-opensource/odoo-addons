# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import api, models


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    @api.model_create_multi
    def create(self, vals_list):
        """Inherit tax_ids from sale order line for Trendyol orders.

        When invoices are created from pickings via stock_picking_invoicing,
        the tax is recalculated from the product's default taxes instead of
        using the sale order line's tax. For Trendyol orders, this causes
        a mismatch because the sale order line uses a price-included tax
        (e.g. KDV %10 Dahil) while the product default is price-excluded
        (e.g. KDV %10), inflating the invoice total.
        """
        lines = super().create(vals_list)
        for line in lines:
            sale_lines = line.move_line_ids.mapped("sale_line_id")
            if not sale_lines:
                continue
            trendyol_lines = sale_lines.filtered(
                lambda l: l.order_id.trendyol_binding_ids
            )
            if not trendyol_lines:
                continue
            line.tax_ids = trendyol_lines.tax_id
        return lines
