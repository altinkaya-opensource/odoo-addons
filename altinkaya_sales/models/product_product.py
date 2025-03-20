import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class ProductProduct(models.Model):
    _inherit = "product.product"

    v_cari_urun = fields.Many2one("res.partner", "Partner Product")

    name_variant = fields.Char(
        compute="_compute_name_variant_report_name", string="Variant Name"
    )

    def _compute_name_variant_report_name(self):
        for record in self:
            res = record.with_context({"display_default_code": False}).name_get()
            record.name_variant = res[0][1] if res else ""
        return True
