# -*- encoding: utf-8 -*-
#
#Created on Oct 12, 2018
#
#@author: dogan
#
from odoo import models, fields, api

class StockRule(models.Model):
    _inherit = 'stock.rule'
    
    def _prepare_mo_vals(self, product_id, product_qty, product_uom, location_id, name, origin, values, bom):
        res = super(StockRule, self)._prepare_mo_vals(product_id, product_qty, product_uom, location_id, name, origin, values, bom)
        
        res.update({'priority':values['priority']})
        
        return res
    