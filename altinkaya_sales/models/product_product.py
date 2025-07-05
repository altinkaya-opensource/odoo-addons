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
            res = record.with_context(**{"display_default_code": False}).name_get()
            record.name_variant = res[0][1] if res else ""
        return True

    def action_open_product_copy_wizard(self):
        """
        Open the product copy wizard for the selected product.
        """
        self.ensure_one()
        return {
            "name": "Product Copy",
            "type": "ir.actions.act_window",
            "res_model": "product.copy.wizard",
            "view_mode": "form",
            "view_type": "form",
            "target": "new",
            "context": {
                "default_product_id": self.id,
                "default_product_tmpl_id": self.product_tmpl_id.id,
            },
        }
