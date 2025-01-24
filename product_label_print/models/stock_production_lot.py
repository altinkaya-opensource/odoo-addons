# Copyright 2022 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo import models


class StockProductionLot(models.Model):
    _inherit = "stock.production.lot"

    def action_print_product_label(self):
        self.ensure_one()
        res = self.product_id.action_print_label()
        return res
