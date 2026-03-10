# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import json
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class HepsiburadaBatchExportWizard(models.TransientModel):
    _name = "hepsiburada.batch.export.wizard"
    _description = "Hepsiburada Batch Export Wizard"

    # Configuration
    backend_id = fields.Many2one(
        "hepsiburada.backend",
    )
    hb_category_id = fields.Many2one(
        "hepsiburada.category",
        string="Hepsiburada Category",
        domain="[('backend_id', '=', backend_id), ('is_leaf', '=', True)]",
    )
    hb_brand_name = fields.Char(
        string="Brand Name",
        default="Altınkaya",
    )
    vat_rate = fields.Float(
        string="VAT Rate (%)",
        default=20.0,
    )

    # Attributes
    attribute_line_ids = fields.One2many(
        "hepsiburada.export.wizard.attribute.line",
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

    @api.onchange("hb_category_id")
    def _onchange_category(self):
        """Load attributes when category changes."""
        self.attribute_line_ids = [(5, 0, 0)]
        if not self.hb_category_id:
            return

        # Sync if no attributes or missing hb_attribute_code (old sync data)
        needs_sync = not self.hb_category_id.attribute_ids or not any(
            self.hb_category_id.attribute_ids.mapped("hb_attribute_code")
        )
        if needs_sync:
            _logger.info(
                "Syncing attributes for category %s (id=%s)...",
                self.hb_category_id.name,
                self.hb_category_id.marketplace_id,
            )
            try:
                self.hb_category_id._sync_attributes()
            except Exception as e:
                _logger.warning("Failed to sync attributes: %s", str(e))
                return {
                    "warning": {
                        "title": _("Attribute Sync Failed"),
                        "message": str(e),
                    }
                }

        _logger.info(
            "Category %s has %d attributes after sync",
            self.hb_category_id.name,
            len(self.hb_category_id.attribute_ids),
        )

        # Auto-filled attributes: values from wizard fields or product data
        auto_filled_values = {
            "merchantSku": _("(Per product: Internal Ref)"),
            "VaryantGroupID": _("(Per product: Internal Ref)"),
            "Barcode": _("(Per product: Barcode)"),
            "UrunAdi": _("(Per product: Product Name)"),
            "UrunAciklamasi": _("(Per product: Description)"),
            "Marka": self.hb_brand_name or _("(Set Brand Name above)"),
            "GarantiSuresi": "24",
            "tax_vat_rate": str(int(self.vat_rate)) if self.vat_rate else "0",
            "kg": _("(Per product: Weight)"),
            "price": _("(Per product: Pricelist Price)"),
            "stock": _("(Per product: Stock Qty)"),
        }
        # Image fields are also auto-filled
        for i in range(1, 11):
            auto_filled_values[f"Image{i}"] = _("(Per product: Image %d)") % i

        lines = []
        for attr in self.hb_category_id.attribute_ids:
            values_list = []
            for val in attr.value_ids:
                values_list.append({"id": val.hb_value_code, "name": val.name})

            attr_code = attr.hb_attribute_code
            is_auto = attr_code in auto_filled_values
            lines.append(
                (
                    0,
                    0,
                    {
                        "attribute_name": attr.name,
                        "attribute_marketplace_id": attr_code,
                        "attribute_id": attr.id,
                        "required": attr.required,
                        "has_values": bool(attr.value_ids),
                        "is_auto_filled": is_auto,
                        "value": auto_filled_values.get(attr_code, False)
                        if is_auto
                        else False,
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
        if not self.hb_category_id:
            raise UserError(_("Please select a category."))
        if not self.hb_brand_name:
            raise UserError(_("Please enter a brand name."))
        if not self.product_ids:
            raise UserError(_("Please select at least one product."))
        for line in self.attribute_line_ids:
            if line.is_auto_filled:
                continue
            if line.required and not line.value and not line.value_id:
                raise UserError(
                    _("Please fill required attribute: %s") % line.attribute_name
                )

    def _create_bindings(self, errors):
        """Create product bindings for selected products.

        Returns:
            Tuple of (created_count, skipped_count)
        """
        Binding = self.env["hepsiburada.product.binding"]
        created = 0
        skipped = 0

        attributes_dict = {}
        for line in self.attribute_line_ids:
            if line.is_auto_filled:
                continue
            val = line.value_id.name if line.value_id else line.value
            if val and line.attribute_marketplace_id:
                # Use HB attribute code as key (e.g. "merchantSku", "Marka")
                attributes_dict[line.attribute_marketplace_id] = val

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
                        "hb_merchant_sku": product.default_code or product.barcode,
                        "hb_category_id": self.hb_category_id.id,
                        "hb_brand_name": self.hb_brand_name,
                        "vat_rate": self.vat_rate,
                    }
                    if attributes_dict:
                        vals["hb_attributes"] = json.dumps(
                            attributes_dict, ensure_ascii=False
                        )
                    Binding.create(vals)
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

        return created, skipped

    def _export_bindings(self, errors):
        """Export draft bindings to Hepsiburada API."""
        Binding = self.env["hepsiburada.product.binding"]
        BatchRequest = self.env["hepsiburada.batch.request"]
        bindings_to_export = Binding.search(
            [
                ("backend_id", "=", self.backend_id.id),
                ("odoo_id", "in", self.product_ids.ids),
                ("sync_state", "=", "draft"),
            ]
        )

        if not bindings_to_export:
            return

        # Prepare product data
        products_data = []
        export_bindings = self.env["hepsiburada.product.binding"]
        for binding in bindings_to_export:
            try:
                data = binding._prepare_product_data()
                products_data.append(data)
                export_bindings |= binding
            except UserError as e:
                errors.append(str(e))

        if not products_data:
            return

        # Create batch request record before API call so it's always visible
        batch_request = BatchRequest.create(
            {
                "backend_id": self.backend_id.id,
                "tracking_id": f"pending-{fields.Datetime.now()}",
                "request_type": "product_create",
                "state": "pending",
                "total_items": len(products_data),
                "product_binding_ids": [(6, 0, export_bindings.ids)],
            }
        )

        # Call API in a savepoint so failures don't rollback the batch request
        try:
            with self.env.cr.savepoint():
                client = self.backend_id._get_api_client()
                result = client.upload_products(products_data)
                # Response: {"success":true,"data":{"trackingId":"..."}}
                data = result.get("data") or {}
                tracking_id = (
                    data.get("trackingId")
                    or result.get("trackingId")
                    or result.get("id")
                )
                if tracking_id:
                    batch_request.tracking_id = str(tracking_id)
                    export_bindings.write(
                        {
                            "sync_state": "pending",
                            "hb_tracking_id": str(tracking_id),
                            "last_sync_date": fields.Datetime.now(),
                        }
                    )
        except Exception as e:
            batch_request.write(
                {
                    "state": "failed",
                    "error_messages": str(e),
                }
            )
            export_bindings.write(
                {
                    "sync_state": "error",
                    "sync_error": str(e),
                }
            )
            errors.append(_("Export failed: %s") % str(e))
            _logger.error("Batch export to Hepsiburada failed: %s", str(e))

    def action_export(self):
        """Validate, create bindings and export products."""
        self.ensure_one()
        self._validate()

        errors = []
        created, skipped = self._create_bindings(errors)
        self._export_bindings(errors)

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
                    "res_model": "hepsiburada.product.binding",
                    "view_mode": "tree,form",
                    "views": [[False, "tree"], [False, "form"]],
                    "domain": [
                        ("backend_id", "=", self.backend_id.id),
                        ("odoo_id", "in", self.product_ids.ids),
                    ],
                },
            },
        }


class HepsiburadaExportWizardAttributeLine(models.TransientModel):
    _name = "hepsiburada.export.wizard.attribute.line"
    _description = "Hepsiburada Export Wizard Attribute Line"

    wizard_id = fields.Many2one(
        "hepsiburada.batch.export.wizard",
        required=True,
        ondelete="cascade",
    )
    attribute_name = fields.Char()
    attribute_marketplace_id = fields.Char(
        string="Attribute Code",
    )
    attribute_id = fields.Many2one(
        "hepsiburada.category.attribute",
    )
    required = fields.Boolean()
    has_values = fields.Boolean()
    is_auto_filled = fields.Boolean(
        string="Auto-filled",
        help="This attribute is automatically filled from product data",
    )
    value = fields.Char()
    value_id = fields.Many2one(
        "hepsiburada.attribute.value",
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
