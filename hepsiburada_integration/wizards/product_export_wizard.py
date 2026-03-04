# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import json
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


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
    odoo_category_id = fields.Many2one(
        "product.category",
        help="Map to Odoo product category for filtering (optional)",
        string="Odoo Category",
    )
    odoo_product_search = fields.Char(
        string="Product Search",
        help="Search products by name or internal reference (optional)",
    )
    hb_category_id = fields.Many2one(
        "hepsiburada.category",
        string="Hepsiburada Category",
        domain="[('backend_id', '=', backend_id), ('is_leaf', '=', True)]",
        help="Category to use for all selected products (optional)",
    )
    hb_brand_id = fields.Many2one(
        "hepsiburada.brand",
        string="Hepsiburada Brand",
        required=True,
        domain="[('backend_id', '=', backend_id)]",
        help="Brand to use for all selected products",
    )
    attribute_line_ids = fields.One2many(
        "hepsiburada.product.export.wizard.line",
        "wizard_id",
        string="Attribute Values",
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

    @api.onchange("hb_category_id")
    def _onchange_hb_category_id(self):
        self.attribute_line_ids = [(5, 0, 0)]
        if self.hb_category_id:
            if not self.hb_category_id.attribute_ids:
                return {
                    "warning": {
                        "title": _("No Attributes"),
                        "message": _(
                            "Attributes have not been loaded yet. "
                            "Click 'Fetch Attributes' button."
                        ),
                    }
                }
            lines = []
            for attr in self.hb_category_id.attribute_ids:
                lines.append(
                    (
                        0,
                        0,
                        {
                            "category_attribute_id": attr.id,
                        },
                    )
                )
            self.attribute_line_ids = lines

    def action_sync_category_attributes(self):
        """Sync attributes for the selected category."""
        self.ensure_one()
        if not self.hb_category_id:
            raise UserError(_("Please select a category first."))
        self.hb_category_id._sync_attributes()
        # Reload lines
        lines = []
        for attr in self.hb_category_id.attribute_ids:
            lines.append(
                (
                    0,
                    0,
                    {
                        "category_attribute_id": attr.id,
                    },
                )
            )
        self.attribute_line_ids = [(5, 0, 0)] + lines
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }

    @api.onchange("odoo_category_id", "odoo_product_search")
    def _onchange_product_filters(self):
        domain = []
        if self.odoo_category_id:
            domain.append(("categ_id", "=", self.odoo_category_id.id))
        if self.odoo_product_search:
            domain += [
                "|",
                ("name", "ilike", self.odoo_product_search),
                ("default_code", "ilike", self.odoo_product_search),
            ]
        if domain:
            self.product_ids = self.env["product.product"].search(domain)

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
        """Create product bindings and export to Hepsiburada."""
        self.ensure_one()

        if not self.product_ids:
            raise UserError(_("Please select at least one product."))

        Binding = self.env["hepsiburada.product.binding"]
        bindings = self.env["hepsiburada.product.binding"]
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

            if not product.barcode and not product.default_code:
                raise UserError(
                    _("Product %s has no barcode or internal reference.")
                    % product.display_name
                )

            vals = {
                "backend_id": self.backend_id.id,
                "odoo_id": product.id,
                "hb_sku": product.barcode or product.default_code,
                "hb_merchant_sku": product.default_code,
                "vat_rate": self.vat_rate,
            }

            if self.hb_category_id:
                vals["hb_category_id"] = self.hb_category_id.id
            if self.hb_brand_id:
                vals["hb_brand_id"] = self.hb_brand_id.id
            if self.attribute_line_ids:
                attrs = {}
                for line in self.attribute_line_ids:
                    hb_attr_id = line.category_attribute_id.hb_attribute_id
                    if line.value_id:
                        attrs[hb_attr_id] = line.value_id.name
                    elif line.custom_value:
                        attrs[hb_attr_id] = line.custom_value
                if attrs:
                    vals["hb_attributes"] = json.dumps(attrs)

            binding = Binding.create(vals)
            bindings |= binding
            created += 1

        if not bindings:
            raise UserError(_("No new bindings to export."))

        # Batch export
        self._batch_export(bindings)

        message = _("%d product(s) exported to Hepsiburada.") % created
        if skipped:
            message += " " + _("%d product(s) skipped (already bound).") % skipped

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Export Started"),
                "message": message,
                "type": "success",
                "sticky": False,
            },
        }

    def _batch_export(self, bindings):
        """Export products in batch to Hepsiburada."""
        client = self.backend_id._get_api_client()
        BatchRequest = self.env["hepsiburada.batch.request"]

        items = []
        for binding in bindings:
            data = binding._prepare_product_data()
            if data:
                items.append(data)

        if not items:
            raise UserError(_("No valid products to export."))

        result = client.upload_products(items)

        data = result.get("data") or {}
        batch_id = data.get("trackingId") or result.get("trackingId")
        if not batch_id:
            _logger.error("HB API did not return trackingId. Response: %s", result)
            raise UserError(
                _("Hepsiburada API did not return a tracking ID. Response: %s")
                % str(result)
            )

        BatchRequest.create(
            {
                "backend_id": self.backend_id.id,
                "batch_request_id": batch_id,
                "request_type": "product_create",
                "state": "pending",
                "total_items": len(items),
                "product_binding_ids": [(6, 0, bindings.ids)],
            }
        )
        bindings.write(
            {
                "sync_state": "pending",
                "last_sync_date": fields.Datetime.now(),
            }
        )


class HepsiburadaProductExportWizardLine(models.TransientModel):
    _name = "hepsiburada.product.export.wizard.line"
    _description = "Hepsiburada Product Export Wizard Attribute Line"

    wizard_id = fields.Many2one(
        "hepsiburada.product.export.wizard",
        required=True,
        ondelete="cascade",
    )
    category_attribute_id = fields.Many2one(
        "hepsiburada.category.attribute",
        string="Attribute",
        readonly=True,
    )
    name = fields.Char(related="category_attribute_id.name", readonly=True)
    required = fields.Boolean(related="category_attribute_id.required", readonly=True)
    allow_custom = fields.Boolean(
        related="category_attribute_id.allow_custom", readonly=True
    )
    attr_type = fields.Char(related="category_attribute_id.attr_type", readonly=True)
    value_id = fields.Many2one(
        "hepsiburada.attribute.value",
        string="Value",
        domain="[('attribute_id', '=', category_attribute_id)]",
    )
    custom_value = fields.Char(string="Custom Value")
