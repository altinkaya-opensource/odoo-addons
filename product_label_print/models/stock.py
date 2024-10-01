# -*- coding: utf-8 -*-

from odoo import api, fields, models, _


class StockMove(models.Model):
    _inherit = "stock.move"

    
    def action_print_product_label(self):

        self.ensure_one()
        res = self.product_id.action_print_label()
        return res


# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
