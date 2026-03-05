# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import models


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    def _compute_price_unit(self):
        """Skip price recomputation for Hepsiburada lines (prices from API)."""
        hb_lines = self.filtered(lambda l: l.order_id.hepsiburada_binding_ids)
        return super(SaleOrderLine, self - hb_lines)._compute_price_unit()
