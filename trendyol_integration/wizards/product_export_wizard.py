# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class TrendyolProductExportWizard(models.TransientModel):
    _name = "trendyol.product.export.wizard"
    _description = "Trendyol Product Export Wizard"

    backend_id = fields.Many2one(
        "trendyol.backend",
        required=True,
    )
    product_ids = fields.Many2many(
        "product.product",
        string="Products",
        required=True,
    )
    trendyol_category_id = fields.Many2one(
        "trendyol.category",
        domain="[('backend_id', '=', backend_id), ('is_leaf', '=', True)]",
        help="Category to use for all selected products (optional)",
    )
    trendyol_brand_id = fields.Many2one(
        "trendyol.brand",
        domain="[('backend_id', '=', backend_id)]",
        help="Brand to use for all selected products (optional)",
    )
    vat_rate = fields.Float(
        string="VAT Rate (%)",
        default=20.0,
    )
    skip_existing = fields.Boolean(
        string="Skip Existing Bindings",
        default=True,
        help="Skip products that already have a binding for this backend",
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
            product_ids = templates.mapped("product_variant_ids").ids
            res["product_ids"] = [(6, 0, product_ids)]

        return res

    def action_create_bindings(self):
        """Create product bindings for selected products."""
        self.ensure_one()

        if not self.product_ids:
            raise UserError(_("Please select at least one product."))

        Binding = self.env["trendyol.product.binding"]
        created = 0
        skipped = 0

        for product in self.product_ids:
            # Check if binding exists
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

            # Validate product
            if not product.barcode and not product.default_code:
                raise UserError(
                    _("Product %s has no barcode or internal reference.")
                    % product.display_name
                )

            # Create binding
            vals = {
                "backend_id": self.backend_id.id,
                "odoo_id": product.id,
                "trendyol_barcode": product.barcode or product.default_code,
                "trendyol_stock_code": product.default_code,
                "vat_rate": self.vat_rate,
            }

            if self.trendyol_category_id:
                vals["trendyol_category_id"] = self.trendyol_category_id.id
            if self.trendyol_brand_id:
                vals["trendyol_brand_id"] = self.trendyol_brand_id.id

            Binding.create(vals)
            created += 1

        message = _("%d product binding(s) created.") % created
        if skipped:
            message += " " + _("%d product(s) skipped (already bound).") % skipped

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
                    "res_model": "trendyol.product.binding",
                    "view_mode": "tree,form",
                    "domain": [
                        ("backend_id", "=", self.backend_id.id),
                        ("odoo_id", "in", self.product_ids.ids),
                    ],
                },
            },
        }
