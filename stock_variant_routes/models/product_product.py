# -*- coding: utf-8 -*-
'''
Created on Jul 18, 2016

@author: Codequarters_ugur
'''

from odoo import models, fields, api
from odoo import Command


class product_product(models.Model):
    _inherit = 'product.product'

    route_ids= fields.Many2many('stock.route', string='Routes', domain="[('product_selectable', '=', True)]",
                                    compute='_compute_variant_routes', store=True)

    variant_route_ids= fields.Many2many('stock.route','stock_route_product_variant', 'product_id', 'route_id',
                                        string='Variant Routes')


    @api.depends('variant_route_ids', 'product_tmpl_id.route_ids')
    def _compute_variant_routes(self):
        for product in self:
            if product.variant_route_ids:
                route_ids = product.variant_route_ids
            else:
                route_ids = product.product_tmpl_id.route_ids

            product.write({'route_ids': [Command.set(route_ids.ids)]})
