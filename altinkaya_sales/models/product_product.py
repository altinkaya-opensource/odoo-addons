# -*- encoding: utf-8 -*-

from odoo import models, fields, api
from odoo.tools import float_is_zero
from odoo.addons import decimal_precision as dp
import logging

_logger = logging.getLogger(__name__)


class ProductProduct(models.Model):
    _inherit = "product.product"

    v_cari_urun = fields.Many2one("res.partner", "Partner Product")

    name_variant = fields.Char(
        compute="_compute_name_variant_report_name", string="Variant Name"
    )



    def _compute_name_variant_report_name(self):
        result = self.with_context({"display_default_code": False}).name_get()
        return result
