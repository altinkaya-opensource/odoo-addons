# -*- encoding: utf-8 -*-
#
#Created on Jan 17, 2020
#
#@author: dogan
#

from odoo import models, fields, api


class ProductCategory(models.Model):
    _inherit="product.category"


    x_guncelleme = fields.Char('Kategori Referansi',size=64,required=False)
    custom_products = fields.Boolean('Custom Products')
