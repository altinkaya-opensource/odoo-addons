# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import models


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    def _is_marketplace_api_priced_line(self):
        return self.order_id._is_marketplace_order()

    def _compute_price_unit(self):
        """Keep marketplace API prices instead of recomputing from pricelists."""
        marketplace_lines = self.filtered(
            lambda line: line._is_marketplace_api_priced_line()
        )
        return super(SaleOrderLine, self - marketplace_lines)._compute_price_unit()
