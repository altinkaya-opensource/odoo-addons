#
# Created on Jan 17, 2020
#
# @author: dogan
#

from odoo import fields, models


class ProductCategory(models.Model):
    _inherit = "product.category"

    custom_products = fields.Boolean()
