# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import json
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from .hepsiburada_request import HepsiburadaAPIError

_logger = logging.getLogger(__name__)


class HepsiburadaProductBinding(models.Model):
    _name = "hepsiburada.product.binding"
    _description = "Hepsiburada Product Binding"
    _inherit = ["marketplace.product.binding"]
    _inherits = {"product.product": "odoo_id"}
    _order = "create_date desc"

    odoo_id = fields.Many2one(
        "product.product",
        string="Odoo Product",
        required=True,
        ondelete="cascade",
        index=True,
    )
    backend_id = fields.Many2one(
        "hepsiburada.backend",
        required=True,
        ondelete="cascade",
        index=True,
    )

    # Hepsiburada identifiers
    hb_merchant_sku = fields.Char(
        string="Merchant SKU",
        required=True,
        index=True,
        help="Unique SKU for this product on Hepsiburada",
    )

    # Mappings
    hb_category_id = fields.Many2one(
        "hepsiburada.category",
        string="Hepsiburada Category",
        required=True,
        domain="[('backend_id', '=', backend_id), ('is_leaf', '=', True)]",
    )
    hb_brand_name = fields.Char(
        string="Brand Name",
        required=True,
        help="Brand name as registered on Hepsiburada",
    )

    # Attributes (stored as JSON)
    hb_attributes = fields.Text(
        string="Attributes",
        help="JSON object of category attributes",
    )

    # Prices
    hb_list_price = fields.Float(
        string="List Price",
        digits="Product Price",
        compute="_compute_prices",
        store=True,
        help="List price from configured pricelist",
    )

    # Stock
    hb_quantity = fields.Float(
        string="Stock Quantity",
        compute="_compute_hb_quantity",
        help="Available quantity for Hepsiburada",
    )

    # Tracking
    hb_tracking_id = fields.Char(
        string="Tracking ID",
        readonly=True,
        help="Tracking ID from last product upload",
    )

    _sql_constraints = [
        (
            "sku_backend_uniq",
            "unique(hb_merchant_sku, backend_id)",
            "Merchant SKU must be unique per backend!",
        ),
        (
            "product_backend_uniq",
            "unique(odoo_id, backend_id)",
            "Product can only be bound once per backend!",
        ),
    ]

    @api.depends("odoo_id", "backend_id", "backend_id.pricelist_id")
    def _compute_prices(self):
        for binding in self:
            if not binding.backend_id.pricelist_id or not binding.odoo_id:
                binding.hb_list_price = 0.0
                continue

            pricelist = binding.backend_id.pricelist_id
            price = pricelist._get_product_price(
                binding.odoo_id,
                quantity=1.0,
                partner=False,
            )
            binding.hb_list_price = price

    @api.depends("odoo_id", "backend_id", "backend_id.warehouse_ids")
    def _compute_hb_quantity(self):
        for binding in self:
            if not binding.backend_id.warehouse_ids or not binding.odoo_id:
                binding.hb_quantity = 0.0
                continue

            total_qty = 0.0
            for warehouse in binding.backend_id.warehouse_ids:
                total_qty += binding.odoo_id.with_context(
                    location=warehouse.lot_stock_id.id
                ).free_qty
            binding.hb_quantity = total_qty

    @api.constrains("hb_merchant_sku")
    def _check_merchant_sku(self):
        for binding in self:
            if not binding.hb_merchant_sku:
                raise ValidationError(_("Merchant SKU is required."))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("hb_merchant_sku") and vals.get("odoo_id"):
                product = self.env["product.product"].browse(vals["odoo_id"])
                vals["hb_merchant_sku"] = product.default_code or product.barcode
        return super().create(vals_list)

    def _prepare_product_data(self):
        """Prepare product data for Hepsiburada API.

        HB API rules:
        - merchantSku: UPPERCASE, no spaces
        - price: comma decimal separator, max 2 decimals (e.g. "14,50")
        - stock: numeric string
        - Barcode: EAN13 format preferred
        - GarantiSuresi: integer (months)
        - Image URLs: HTTPS, PNG/JPG only

        Returns:
            Dict with product data matching HB API format
        """
        self.ensure_one()

        if not self.hb_category_id:
            raise UserError(
                _("Hepsiburada category is required for product %s") % self.display_name
            )

        product = self.odoo_id
        image_url = self._get_image_url(product)
        description = self._get_description(product)
        price = self.hb_list_price

        if not price or price <= 0:
            raise UserError(
                _("Product price must be greater than 0 for %s") % self.display_name
            )

        # merchantSku must be UPPERCASE with no spaces (HB auto-converts anyway)
        merchant_sku = (self.hb_merchant_sku or "").upper().replace(" ", "")
        if not merchant_sku:
            raise UserError(
                _("Merchant SKU is required for product %s") % self.display_name
            )

        # Price: comma as decimal separator, max 2 decimal places
        price_str = f"{price:.2f}".replace(".", ",")

        # Build attributes dict
        attributes = {
            "merchantSku": merchant_sku,
            "VaryantGroupID": merchant_sku,
            "Barcode": product.barcode or merchant_sku,
            "UrunAdi": product.name[:500],
            "UrunAciklamasi": description,
            "Marka": self.hb_brand_name,
            "GarantiSuresi": 24,
            "kg": str(product.weight) if product.weight else "1",
            "tax_vat_rate": str(int(self.vat_rate)),
            "price": price_str,
            "stock": str(int(max(0, self.hb_quantity))),
        }

        # Image1 is required
        if image_url:
            attributes["Image1"] = image_url

        # Add extra images (up to Image5 per HB docs)
        if hasattr(product, "product_image_ids"):
            for i, img in enumerate(product.product_image_ids[:4], start=2):
                img_url = (
                    self._get_image_url(img) if hasattr(img, "image_url") else None
                )
                if img_url:
                    attributes[f"Image{i}"] = img_url

        # Merge custom attributes from JSON
        if self.hb_attributes:
            try:
                custom_attrs = json.loads(self.hb_attributes)
                if isinstance(custom_attrs, dict):
                    attributes.update(custom_attrs)
            except (json.JSONDecodeError, TypeError):
                _logger.debug("Invalid JSON in hb_attributes for %s", self.display_name)

        return {
            "categoryId": self.hb_category_id.marketplace_id,
            "merchant": self.backend_id.merchant_id,
            "attributes": attributes,
        }

    def action_export_to_hepsiburada(self):
        """Export product to Hepsiburada."""
        self.ensure_one()
        self.with_delay(
            channel="root.hepsiburada.product",
            description=_("Export product to Hepsiburada: %s") % self.display_name,
        )._export_to_hepsiburada()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Export Started"),
                "message": _("Product export has been queued."),
                "type": "info",
                "sticky": False,
            },
        }

    def _export_to_hepsiburada(self):
        """Export product to Hepsiburada API."""
        self.ensure_one()
        client = self.backend_id._get_api_client()

        try:
            data = self._prepare_product_data()
            result = client.upload_products([data])

            # Response: {"success":true,"data":{"trackingId":"..."}}
            result_data = result.get("data") or {}
            tracking_id = (
                result_data.get("trackingId")
                or result.get("trackingId")
                or result.get("id")
            )
            if tracking_id:
                self.hb_tracking_id = str(tracking_id)
                self.sync_state = "pending"
                self.last_sync_date = fields.Datetime.now()
                _logger.info(
                    "Exported product %s, tracking: %s",
                    self.display_name,
                    tracking_id,
                )
        except HepsiburadaAPIError as e:
            self.sync_state = "error"
            self.sync_error = str(e)
            _logger.error(
                "Failed to export product %s: %s",
                self.display_name,
                str(e),
            )
            raise
        except UserError as e:
            self.sync_state = "error"
            self.sync_error = str(e)
            raise

    def action_check_status(self):
        """Check product status on Hepsiburada."""
        self.ensure_one()
        if not self.hb_tracking_id:
            raise UserError(_("No tracking ID found for this product."))

        client = self.backend_id._get_api_client()
        try:
            result = client.get_product_status(self.hb_tracking_id)
            # Find this product's item in data array
            items = result.get("data") or []
            sku = (self.hb_merchant_sku or "").upper()
            my_item = next((i for i in items if i.get("merchantSku") == sku), None)
            if my_item:
                product_status = my_item.get("productStatus", "")
                import_status = my_item.get("importStatus", "")
                errors = []
                for vr in my_item.get("validationResults") or []:
                    errors.append(vr.get("message", str(vr)))
                self.sync_error = (
                    f"{product_status} ({import_status})\n" + "\n".join(errors)
                ).strip()
                if my_item.get("hbSku"):
                    self.marketplace_id = my_item["hbSku"]
                _logger.info(
                    "Product %s status: %s / %s",
                    self.display_name,
                    import_status,
                    product_status,
                )
            else:
                self.sync_error = json.dumps(result, indent=2, ensure_ascii=False)
        except HepsiburadaAPIError as e:
            raise UserError(_("Failed to check status: %s") % str(e)) from e

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Status Checked"),
                "message": _("Check sync error field for details."),
                "type": "info",
                "sticky": False,
            },
        }
