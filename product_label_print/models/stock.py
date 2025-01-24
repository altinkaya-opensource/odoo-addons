from odoo import models


class StockMove(models.Model):
    _inherit = "stock.move"

    def action_print_product_label(self):
        self.ensure_one()
        res = self.product_id.action_print_label()
        return res
