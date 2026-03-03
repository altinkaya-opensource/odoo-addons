# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import json
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


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
    odoo_category_id = fields.Many2one(
        "product.category",
        help="Map to Odoo product category for filtering (optional)",
    )
    odoo_product_search = fields.Char(
        string="Product Search",
        help="Search products by name or internal reference (optional)",
    )
    trendyol_category_id = fields.Many2one(
        "trendyol.category",
        domain="[('backend_id', '=', backend_id), ('is_leaf', '=', True)]",
        help="Category to use for all selected products (optional)",
    )
    trendyol_brand_id = fields.Many2one(
        "trendyol.brand",
        required=True,
        domain="[('backend_id', '=', backend_id)]",
        help="Brand to use for all selected products (optional)",
    )
    attribute_line_ids = fields.One2many(
        "trendyol.product.export.wizard.line",
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

    @api.onchange("trendyol_category_id")
    def _onchange_trendyol_category_id(self):
        self.attribute_line_ids = [(5, 0, 0)]
        if self.trendyol_category_id:
            if not self.trendyol_category_id.attribute_ids:
                return {
                    "warning": {
                        "title": _("No Attributes"),
                        "message": _(
                            "Attribute'lar henüz yüklenmemiş. "
                            "'Özellikleri Getir' butonuna basın."
                        ),
                    }
                }
            lines = []
            for attr in self.trendyol_category_id.attribute_ids:
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
        self.ensure_one()
        if not self.trendyol_category_id:
            raise UserError(_("Please select a category first."))
        self.trendyol_category_id._sync_attributes()
        # Reload lines
        lines = []
        for attr in self.trendyol_category_id.attribute_ids:
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

    def _create_binding_for_product(self, product):
        """Create a product binding record for one product.

        Returns the new binding, or raises UserError if not possible.
        """
        Binding = self.env["trendyol.product.binding"]
        existing = Binding.search(
            [("backend_id", "=", self.backend_id.id), ("odoo_id", "=", product.id)],
            limit=1,
        )
        if existing:
            if self.skip_existing:
                return None
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
            "trendyol_barcode": product.barcode or product.default_code,
            "trendyol_stock_code": product.default_code,
            "vat_rate": self.vat_rate,
        }
        if self.trendyol_category_id:
            vals["trendyol_category_id"] = self.trendyol_category_id.id
        if self.trendyol_brand_id:
            vals["trendyol_brand_id"] = self.trendyol_brand_id.id

        attrs = []
        for line in self.attribute_line_ids:
            if line.value_id:
                attrs.append(
                    {
                        "attributeId": line.category_attribute_id.trendyol_id,
                        "attributeValueId": line.value_id.trendyol_id,
                    }
                )
            elif line.custom_value:
                attrs.append(
                    {
                        "attributeId": line.category_attribute_id.trendyol_id,
                        "customAttributeValue": line.custom_value,
                    }
                )
        if attrs:
            vals["trendyol_attributes"] = json.dumps(attrs)

        return Binding.create(vals)

    def action_create_bindings(self):
        """Create product bindings and export to Trendyol."""
        self.ensure_one()

        if not self.product_ids:
            raise UserError(_("Please select at least one product."))

        bindings = self.env["trendyol.product.binding"]
        created = 0
        skipped = 0

        for product in self.product_ids:
            try:
                with self.env.cr.savepoint():
                    binding = self._create_binding_for_product(product)
            except Exception as e:
                _logger.warning(
                    "Failed to create binding for product %s: %s",
                    product.display_name,
                    str(e),
                )
                skipped += 1
                continue
            if binding:
                bindings |= binding
                created += 1
            else:
                skipped += 1

        if not bindings:
            raise UserError(_("No new bindings to export."))

        # Attempt export in a savepoint so binding records always persist.
        # If the API call fails, bindings remain in draft state for manual retry.
        export_error = None
        try:
            with self.env.cr.savepoint():
                self._batch_export(bindings)
        except Exception as e:
            _logger.exception(
                "Trendyol export failed for %d bindings: %s", len(bindings), str(e)
            )
            export_error = str(e)

        if export_error:
            message = _(
                "%(count)d binding(s) created but export failed: %(error)s. "
                "Please retry from the Trendyol Products menu."
            ) % {"count": created, "error": export_error}
            if skipped:
                message += " " + _("%d product(s) skipped (already bound).") % skipped
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Bindings Created — Export Failed"),
                    "message": message,
                    "type": "warning",
                    "sticky": True,
                },
            }

        message = _("%d binding(s) created and export started.") % created
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
        """Export products in batch to Trendyol."""
        client = self.backend_id._get_api_client()
        BatchRequest = self.env["trendyol.batch.request"]

        items = []
        for binding in bindings:
            data = binding._prepare_product_data()
            if data:
                items.append(data)

        if not items:
            raise UserError(_("No valid products to export."))

        result = client.create_products(items)
        _logger.info("Trendyol create_products response: %s", result)

        batch_id = result.get("batchRequestId")
        if not batch_id:
            raise UserError(
                _("Trendyol API did not return a batchRequestId. Full response: %s")
                % result
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


class TrendyolProductExportWizardLine(models.TransientModel):
    _name = "trendyol.product.export.wizard.line"
    _description = "Trendyol Product Export Wizard Attribute Line"
    wizard_id = fields.Many2one(
        "trendyol.product.export.wizard",
        required=True,
        ondelete="cascade",
    )
    category_attribute_id = fields.Many2one(
        "trendyol.category.attribute",
        string="Attribute",
        readonly=True,
    )
    name = fields.Char(related="category_attribute_id.name", readonly=True)
    required = fields.Boolean(related="category_attribute_id.required", readonly=True)
    allow_custom = fields.Boolean(
        related="category_attribute_id.allow_custom", readonly=True
    )
    value_id = fields.Many2one(
        "trendyol.attribute.value",
        domain="[('attribute_id', '=', category_attribute_id)]",
    )
    custom_value = fields.Char()
