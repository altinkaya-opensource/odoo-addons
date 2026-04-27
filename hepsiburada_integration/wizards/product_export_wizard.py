# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class HepsiburadaProductExportWizard(models.TransientModel):
    _name = "hepsiburada.product.export.wizard"
    _description = "Hepsiburada Product Export Wizard"

    backend_id = fields.Many2one(
        "hepsiburada.backend",
        required=True,
    )
    product_ids = fields.Many2many(
        "product.product",
        string="Products",
        required=True,
    )
    hepsiburada_category_id = fields.Many2one(
        "hepsiburada.category",
        domain="[('backend_id', '=', backend_id), ('is_leaf', '=', True)]",
        help="Category to use for all selected products (optional)",
    )
    hepsiburada_brand_id = fields.Many2one(
        "hepsiburada.brand",
        domain="[('backend_id', '=', backend_id)]",
        help="Brand to use for all selected products (optional)",
    )
    vat_rate = fields.Float(
        string="VAT Rate (%)",
        default=20.0,
    )
    dispatch_time = fields.Integer(
        string="Dispatch Time (days)",
        default=1,
    )
    skip_existing = fields.Boolean(
        string="Skip Existing Bindings",
        default=True,
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        active_ids = self.env.context.get("active_ids", [])
        active_model = self.env.context.get("active_model")
        if active_model == "product.product":
            res["product_ids"] = [(6, 0, active_ids)]
        elif active_model == "product.template":
            templates = self.env["product.template"].browse(active_ids)
            res["product_ids"] = [(6, 0, templates.mapped("product_variant_ids").ids)]
        return res

    def action_create_bindings(self):
        self.ensure_one()
        if not self.product_ids:
            raise UserError(_("Please select at least one product."))

        Binding = self.env["hepsiburada.product.binding"]
        created = 0
        skipped = 0
        for product in self.product_ids:
            existing = Binding.search(
                [
                    ("backend_id", "=", self.backend_id.id),
                    ("odoo_id", "=", product.id),
                ],
                limit=1,
            )
            if existing:
                if self.skip_existing:
                    skipped += 1
                    continue
                raise UserError(
                    _("Product %s already has a binding for this backend.")
                    % product.display_name
                )
            if not product.default_code and not product.barcode:
                raise UserError(
                    _("Product %s has no internal reference or barcode.")
                    % product.display_name
                )
            vals = {
                "backend_id": self.backend_id.id,
                "odoo_id": product.id,
                "merchant_sku": product.default_code or product.barcode,
                "vat_rate": self.vat_rate,
                "dispatch_time": self.dispatch_time,
            }
            if self.hepsiburada_category_id:
                vals["hepsiburada_category_id"] = self.hepsiburada_category_id.id
            if self.hepsiburada_brand_id:
                vals["hepsiburada_brand_id"] = self.hepsiburada_brand_id.id
            Binding.create(vals)
            created += 1

        message = _("%d Hepsiburada binding(s) created.") % created
        if skipped:
            message += " " + _("%d skipped (already bound).") % skipped
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Bindings Created"),
                "message": message,
                "type": "success",
                "sticky": False,
                "next": {
                    "type": "ir.actions.act_window",
                    "name": _("Created Bindings"),
                    "res_model": "hepsiburada.product.binding",
                    "view_mode": "tree,form",
                    "domain": [
                        ("backend_id", "=", self.backend_id.id),
                        ("odoo_id", "in", self.product_ids.ids),
                    ],
                },
            },
        }
