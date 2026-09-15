import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class ProductProduct(models.Model):
    _inherit = "product.product"

    v_cari_urun = fields.Many2one("res.partner", "Partner Product")

    name_variant = fields.Char(
        compute="_compute_name_variant_report_name", string="Variant Name"
    )

    @api.model
    def default_get(self, fields_list):
        """Initialize shared variant fields from the selected template."""
        defaults = super().default_get(fields_list)
        template_id = defaults.get("product_tmpl_id") or self.env.context.get(
            "default_product_tmpl_id"
        )
        template = self.env["product.template"].browse(template_id).exists()
        if not template:
            return defaults

        for name in fields_list:
            field = self._fields.get(name)
            if (
                field
                and field.inherited
                and not field.readonly
                and field.type != "one2many"
                and f"default_{name}" not in self.env.context
            ):
                defaults[name] = field.convert_to_write(template[name], template)
        return defaults

    @api.model_create_multi
    def create(self, vals_list):
        """
        When creating a variant with an existing template, the UI sends ALL
        visible fields including inherited ones. The ORM then writes these
        to the parent template triggering modified() on every field, which
        marks all dependent computed fields for recomputation.

        To avoid this, we remove inherited fields from vals before calling
        create on super.
        """
        for vals in vals_list:
            if vals.get("product_tmpl_id"):
                # Get all inherited field names (fields from product.template)
                inherited_fnames = [
                    fname for fname, field in self._fields.items() if field.inherited
                ]
                # Remove them from vals - they already exist on the template
                for fname in inherited_fnames:
                    vals.pop(fname, None)
        return super().create(vals_list)

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
