# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import json
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class TrendyolBatchExportWizard(models.TransientModel):
    _name = "trendyol.batch.export.wizard"
    _description = "Trendyol Batch Export Wizard"

    # Configuration
    backend_id = fields.Many2one(
        "trendyol.backend",
    )
    trendyol_category_id = fields.Many2one(
        "trendyol.category",
        domain="[('backend_id', '=', backend_id), ('is_leaf', '=', True)]",
    )
    trendyol_brand_id = fields.Many2one(
        "trendyol.brand",
        domain="[('backend_id', '=', backend_id)]",
    )
    vat_rate = fields.Float(
        string="VAT Rate (%)",
        default=20.0,
    )

    # Attributes
    attribute_line_ids = fields.One2many(
        "trendyol.export.wizard.attribute.line",
        "wizard_id",
        string="Attributes",
    )

    # Product Filters
    category_filter_id = fields.Many2one(
        "product.category",
        string="Odoo Category",
    )
    product_search = fields.Char(
        string="Search Products",
        help="Search by name, internal reference or barcode",
    )
    skip_existing = fields.Boolean(
        string="Skip Existing Bindings",
        default=True,
    )
    website_published_filter = fields.Boolean(
        string="Website Published Only",
        help="Filter only products published on the website",
    )

    # Products
    product_ids = fields.Many2many(
        "product.product",
        string="Products",
    )
    product_count = fields.Integer(
        compute="_compute_product_count",
    )

    @api.depends("product_ids")
    def _compute_product_count(self):
        for wizard in self:
            wizard.product_count = len(wizard.product_ids)

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

    @api.onchange("trendyol_category_id")
    def _onchange_category(self):
        """Load attributes when category changes."""
        self.attribute_line_ids = [(5, 0, 0)]
        if not self.trendyol_category_id:
            return

        # Sync attributes if not yet loaded
        if not self.trendyol_category_id.attribute_ids:
            try:
                self.trendyol_category_id._sync_attributes()
            except Exception as e:
                _logger.warning("Failed to sync attributes: %s", str(e))
                return

        lines = []
        for attr in self.trendyol_category_id.attribute_ids:
            values_list = []
            for val in attr.value_ids:
                values_list.append({"id": val.marketplace_id, "name": val.name})

            lines.append(
                (
                    0,
                    0,
                    {
                        "attribute_name": attr.name,
                        "attribute_marketplace_id": attr.marketplace_id,
                        "attribute_id": attr.id,
                        "required": attr.required,
                        "allow_custom": attr.allow_custom,
                        "has_values": bool(attr.value_ids),
                        "allowed_values_json": json.dumps(
                            values_list, ensure_ascii=False
                        ),
                    },
                )
            )
        self.attribute_line_ids = lines

    @api.onchange("category_filter_id")
    def _onchange_category_filter(self):
        """Load products from selected Odoo category."""
        if self.category_filter_id:
            products = self.env["product.product"].search(
                [("categ_id", "child_of", self.category_filter_id.id)]
            )
            self.product_ids = [(6, 0, products.ids)]
        else:
            self.product_ids = [(5, 0, 0)]
        self.product_search = False

    @api.onchange("website_published_filter")
    def _onchange_website_published_filter(self):
        """Filter current product list by website publish status."""
        if self.website_published_filter:
            if self.product_ids:
                published = self.product_ids.filtered("is_published")
                self.product_ids = [(6, 0, published.ids)]
        elif self.category_filter_id:
            products = self.env["product.product"].search(
                [("categ_id", "child_of", self.category_filter_id.id)]
            )
            self.product_ids = [(6, 0, products.ids)]

    @api.onchange("product_search")
    def _onchange_product_search(self):
        """Filter within loaded products by name, code or barcode."""
        if not self.product_search:
            # Reset to full category set
            if self.category_filter_id:
                products = self.env["product.product"].search(
                    [("categ_id", "child_of", self.category_filter_id.id)]
                )
                self.product_ids = [(6, 0, products.ids)]
            return

        domain = [("id", "in", self.product_ids.ids)]
        term = self.product_search
        domain += [
            "|",
            "|",
            ("name", "ilike", term),
            ("default_code", "ilike", term),
            ("barcode", "ilike", term),
        ]
        products = self.env["product.product"].search(domain)
        self.product_ids = [(6, 0, products.ids)]

    def _validate(self):
        """Validate wizard fields before export."""
        self.ensure_one()
        if not self.backend_id:
            raise UserError(_("Please select a backend."))
        if not self.trendyol_category_id:
            raise UserError(_("Please select a category."))
        if not self.trendyol_brand_id:
            raise UserError(_("Please select a brand."))
        if not self.product_ids:
            raise UserError(_("Please select at least one product."))
        for line in self.attribute_line_ids:
            if line.required and not line.value and not line.value_id:
                raise UserError(
                    _("Please fill required attribute: %s") % line.attribute_name
                )

    def _build_attributes_json(self):
        """Build Trendyol attributes JSON from wizard lines.

        Returns:
            List of attribute dicts for Trendyol API
        """
        attributes = []
        for line in self.attribute_line_ids:
            if not line.value and not line.value_id:
                continue

            attr_dict = {"attributeId": line.attribute_marketplace_id}

            if line.value_id:
                attr_dict["attributeValueId"] = line.value_id.marketplace_id
            elif line.value:
                attr_dict["customAttributeValue"] = line.value

            attributes.append(attr_dict)
        return attributes

    def action_export(self):
        """Validate, create bindings and export products to Trendyol."""
        self.ensure_one()
        self._validate()

        Binding = self.env["trendyol.product.binding"]
        BatchRequest = self.env["trendyol.batch.request"]
        created = 0
        skipped = 0
        errors = []

        attributes_json = json.dumps(self._build_attributes_json(), ensure_ascii=False)

        bindings = self.env["trendyol.product.binding"]

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
                errors.append(
                    _("Product %s has no barcode or internal reference.")
                    % product.display_name
                )
                continue

            try:
                with self.env.cr.savepoint():
                    vals = {
                        "backend_id": self.backend_id.id,
                        "odoo_id": product.id,
                        "trendyol_barcode": product.barcode or product.default_code,
                        "trendyol_stock_code": product.default_code,
                        "trendyol_category_id": self.trendyol_category_id.id,
                        "trendyol_brand_id": self.trendyol_brand_id.id,
                        "vat_rate": self.vat_rate,
                        "trendyol_attributes": attributes_json,
                    }
                    binding = Binding.create(vals)
                    bindings |= binding
                    created += 1
            except Exception as e:
                errors.append(
                    _(
                        "Failed to create binding for %(product)s: %(error)s",
                        product=product.display_name,
                        error=str(e),
                    )
                )
                _logger.warning(
                    "Failed to create binding for %s: %s",
                    product.display_name,
                    str(e),
                )

        # Export all created bindings in batch
        if bindings:
            self._send_to_trendyol(bindings, BatchRequest, errors)

        message = _("%d product binding(s) created.") % created
        if skipped:
            message += " " + _("%d product(s) skipped (already bound).") % skipped
        if errors:
            message += "\n" + "\n".join(errors)

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Export Complete"),
                "message": message,
                "type": "warning" if errors else "success",
                "sticky": bool(errors),
                "next": {
                    "type": "ir.actions.act_window",
                    "name": _("Product Bindings"),
                    "res_model": "trendyol.product.binding",
                    "view_mode": "tree,form",
                    "views": [[False, "tree"], [False, "form"]],
                    "domain": [
                        ("backend_id", "=", self.backend_id.id),
                        ("odoo_id", "in", self.product_ids.ids),
                    ],
                },
            },
        }

    def _send_to_trendyol(self, bindings, BatchRequest, errors):
        """Send bindings to Trendyol API in batches."""
        try:
            with self.env.cr.savepoint():
                products_data = []
                export_bindings = self.env["trendyol.product.binding"]
                for binding in bindings:
                    try:
                        data = binding._prepare_product_data()
                        products_data.append(data)
                        export_bindings |= binding
                    except UserError as e:
                        errors.append(str(e))

                if products_data:
                    client = self.backend_id._get_api_client()
                    # Send in batches of 1000
                    for i in range(0, len(products_data), 1000):
                        batch_items = products_data[i : i + 1000]
                        result = client.create_products(batch_items)
                        batch_id = result.get("batchRequestId")
                        if batch_id:
                            batch_bindings = export_bindings[i : i + 1000]
                            BatchRequest.create(
                                {
                                    "backend_id": self.backend_id.id,
                                    "batch_request_id": batch_id,
                                    "request_type": "product_create",
                                    "state": "pending",
                                    "total_items": len(batch_items),
                                    "product_binding_ids": [(6, 0, batch_bindings.ids)],
                                }
                            )
                    export_bindings.write(
                        {
                            "sync_state": "pending",
                            "last_sync_date": fields.Datetime.now(),
                        }
                    )
        except Exception as e:
            errors.append(_("Export failed: %s") % str(e))
            _logger.error("Batch export to Trendyol failed: %s", str(e))


class TrendyolExportWizardAttributeLine(models.TransientModel):
    _name = "trendyol.export.wizard.attribute.line"
    _description = "Trendyol Export Wizard Attribute Line"

    wizard_id = fields.Many2one(
        "trendyol.batch.export.wizard",
        required=True,
        ondelete="cascade",
    )
    attribute_name = fields.Char()
    attribute_marketplace_id = fields.Integer()
    attribute_id = fields.Many2one(
        "trendyol.category.attribute",
    )
    required = fields.Boolean()
    allow_custom = fields.Boolean()
    has_values = fields.Boolean()
    value = fields.Char()
    value_id = fields.Many2one(
        "trendyol.attribute.value",
        domain="[('attribute_id', '=', attribute_id)]",
    )
    allowed_values_json = fields.Text(
        string="Allowed Values (JSON)",
        help="JSON list of allowed values for this attribute",
    )

    @api.onchange("value_id")
    def _onchange_value_id(self):
        if self.value_id:
            self.value = self.value_id.name
