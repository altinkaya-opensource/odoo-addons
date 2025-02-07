# -*- encoding: utf-8 -*-
#
#Created on Jan 17, 2020
#
#@author: dogan
#

from odoo import models, fields, api


class ProductCategory(models.Model):
    _inherit="product.category"

    custom_products = fields.Boolean('Custom Products')
