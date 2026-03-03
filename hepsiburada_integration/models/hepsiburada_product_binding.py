# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import json
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .hepsiburada_request import HepsiburadaAPIError

_logger = logging.getLogger(__name__)


class HepsiburadaProductBinding(models.Model):
    _name = "hepsiburada.product.binding"
    _inherit = "marketplace.product.binding"
    _description = "Hepsiburada Product Binding"
    _inherits = {"product.product": "odoo_id"}

    backend_id = fields.Many2one(
        "hepsiburada.backend",
        required=True,
        ondelete="cascade",
        index=True,
    )

    # Hepsiburada identifiers
    hb_sku = fields.Char(
        string="Hepsiburada SKU",
        required=True,
        index=True,
        help="SKU used in Hepsiburada listing",
    )
    hb_listing_id = fields.Char(
        string="Listing ID",
        readonly=True,
        index=True,
        help="Listing ID assigned by Hepsiburada after approval",
    )
    hb_merchant_sku = fields.Char(
        string="Merchant SKU",
        help="Your internal merchant SKU",
    )

    # Mappings
    hb_category_id = fields.Many2one(
        "hepsiburada.category",
        domain="[('backend_id', '=', backend_id), ('is_leaf', '=', True)]",
    )
    hb_brand_id = fields.Many2one(
        "hepsiburada.brand",
        domain="[('backend_id', '=', backend_id)]",
    )

    # Attributes (JSON)
    hb_attributes = fields.Text(
        string="Attributes JSON",
        help="JSON representation of category attributes for this product",
    )

    # Prices
    hb_list_price = fields.Float(
        string="List Price",
        digits="Product Price",
        compute="_compute_prices",
        store=True,
        help="List price in TRY from configured pricelist",
    )
    hb_sale_price = fields.Float(
        string="Sale Price",
        digits="Product Price",
        help="Sale price in TRY (if different from list price)",
    )

    # Stock
    hb_quantity = fields.Float(
        compute="_compute_hb_quantity",
        help="Available quantity for Hepsiburada",
    )

    _sql_constraints = [
        (
            "sku_backend_uniq",
            "unique(hb_sku, backend_id)",
            "SKU must be unique per backend!",
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
            try:
                price = pricelist._get_product_price(
                    binding.odoo_id,
                    quantity=1.0,
                    partner=False,
                )
                binding.hb_list_price = price
            except (UserError, ValueError):
                _logger.warning(
                    "Failed to compute price for %s with pricelist %s",
                    binding.odoo_id.display_name,
                    pricelist.display_name,
                )
                binding.hb_list_price = 0.0

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

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("hb_sku") and vals.get("odoo_id"):
                product = self.env["product.product"].browse(vals["odoo_id"])
                vals["hb_sku"] = product.barcode or product.default_code
            if not vals.get("hb_merchant_sku") and vals.get("odoo_id"):
                product = self.env["product.product"].browse(vals["odoo_id"])
                vals["hb_merchant_sku"] = product.default_code
        return super().create(vals_list)

    def _prepare_product_data(self):
        """Prepare product data for Hepsiburada catalog upload API.

        HB catalog upload format (all fields inside attributes):
        {categoryId, merchant, attributes: {merchantSku, Barcode, UrunAdi,
         Marka, price, stock, tax_vat_rate, Image1, ...}}

        Returns:
            Dict with product data for API, or None if invalid.
        """
        self.ensure_one()

        merchant_sku = self.hb_merchant_sku or self.default_code or self.hb_sku
        if not merchant_sku:
            _logger.warning(
                "No merchant SKU for product %s, skipping", self.display_name
            )
            return None

        # Format price as comma-separated string (HB format: "130,50")
        sale_price = self.hb_sale_price or self.hb_list_price
        price_str = f"{sale_price:.2f}".replace(".", ",") if sale_price else "0,00"
        stock_str = str(int(max(0, self.hb_quantity)))

        attributes = {
            "merchantSku": merchant_sku,
            "VaryantGroupID": merchant_sku,
            "Barcode": self.barcode or self.hb_sku,
            "UrunAdi": self.display_name,
            "HepsiBuradaSKU": self.hb_sku,
            "price": price_str,
            "stock": stock_str,
            "tax_vat_rate": str(int(self.vat_rate)),
        }

        # Brand name (mandatory for HB)
        if self.hb_brand_id:
            attributes["Marka"] = self.hb_brand_id.name

        # Product description
        description = (
            self.odoo_id.description_sale
            or self.odoo_id.description
            or self.display_name
        )
        if description:
            attributes["UrunAciklamasi"] = description

        # Product image URL
        image_url = self._get_image_url()
        if image_url:
            attributes["Image1"] = image_url

        # Product weight
        if self.odoo_id.weight:
            attributes["kg"] = str(self.odoo_id.weight)

        # Parse extra attributes from JSON if available
        if self.hb_attributes:
            try:
                extra_attrs = json.loads(self.hb_attributes)
                if isinstance(extra_attrs, dict):
                    attributes.update(extra_attrs)
                elif isinstance(extra_attrs, list):
                    # Convert list format to flat dict
                    for attr in extra_attrs:
                        attr_id = attr.get("attributeId")
                        if not attr_id:
                            continue
                        value = attr.get("attributeValueId") or attr.get(
                            "customAttributeValue"
                        )
                        if value:
                            attributes[attr_id] = value
            except (json.JSONDecodeError, TypeError):
                _logger.warning(
                    "Invalid hb_attributes JSON for product %s",
                    self.display_name,
                )

        data = {"merchant": self.backend_id.merchant_id, "attributes": attributes}

        if self.hb_category_id:
            data["categoryId"] = int(self.hb_category_id.hb_category_id)

        return data

    def _get_image_url(self):
        """Get HTTPS image URL for the product.

        Returns:
            str or None: HTTPS URL for product image.
        """
        if self.odoo_id.image_url:
            url = self.odoo_id.image_url
            if url.startswith("https://"):
                return url
            if url.startswith("http://"):
                return url.replace("http://", "https://", 1)

        base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url")
        if base_url and self.odoo_id.image_1920:
            return f"{base_url}/web/image/product.product/{self.odoo_id.id}/image_1920"
        return None

    def _prepare_stock_price_data(self):
        """Prepare stock/price update data for Hepsiburada listing API.

        Uses the inventory-uploads endpoint field names:
        HepsiburadaSku, MerchantSku, AvailableStock, Price,
        DispatchTime, CargoCompany1.

        Returns:
            Dict with stock/price data or None if no changes.
        """
        self.ensure_one()

        quantity = int(max(0, self.hb_quantity))
        list_price = self.hb_list_price
        sale_price = self.hb_sale_price or list_price

        if quantity == self.last_sent_quantity and sale_price == self.last_sent_price:
            return None

        data = {
            "HepsiburadaSku": self.hb_sku,
            "MerchantSku": self.hb_merchant_sku or self.default_code or self.hb_sku,
            "AvailableStock": quantity,
            "Price": sale_price,
            "DispatchTime": self.backend_id.dispatch_days or 3,
        }

        # Cargo company (required by inventory-uploads)
        carrier = self.backend_id.default_cargo_company_id
        if carrier:
            data["CargoCompany1"] = carrier.name

        return data

    def action_export_to_hepsiburada(self):
        """Export product to Hepsiburada."""
        self.ensure_one()
        self.with_delay(
            channel="root.hepsiburada.order",
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
        """Export product to Hepsiburada catalog API (multipart upload)."""
        self.ensure_one()
        client = self.backend_id._get_api_client()

        try:
            data = self._prepare_product_data()
            if not data:
                return
            result = client.upload_products([data])
            result_data = result.get("data") or {}
            tracking_id = result_data.get("trackingId") or result.get(
                "trackingId"
            )
            if not tracking_id:
                self.sync_state = "error"
                self.sync_error = _(
                    "API did not return tracking ID: %s"
                ) % str(result)
                _logger.error(
                    "HB API missing trackingId for %s: %s",
                    self.display_name,
                    result,
                )
                return
            self.env["hepsiburada.batch.request"].create(
                {
                    "backend_id": self.backend_id.id,
                    "batch_request_id": str(tracking_id),
                    "request_type": "product_create",
                    "state": "pending",
                    "total_items": 1,
                    "product_binding_ids": [(4, self.id)],
                }
            )
            self.sync_state = "pending"
            self.last_sync_date = fields.Datetime.now()
            _logger.info("Exported product %s to Hepsiburada", self.display_name)
        except HepsiburadaAPIError as e:
            self.sync_state = "error"
            self.sync_error = str(e)
            _logger.error(
                "Failed to export product %s to HB: %s", self.display_name, str(e)
            )
            raise

    def action_sync_stock_price(self):
        """Sync stock and price for this product."""
        self.ensure_one()
        if self.sync_state != "approved":
            raise UserError(_("Only approved products can have stock/price synced."))

        self.with_delay(
            channel="root.hepsiburada.order",
            description=_("Sync HB stock/price: %s") % self.display_name,
        )._sync_stock_price()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Sync Started"),
                "message": _("Stock/price sync has been queued."),
                "type": "info",
                "sticky": False,
            },
        }

    def _sync_stock_price(self):
        """Sync stock and price to Hepsiburada listing API."""
        self.ensure_one()
        client = self.backend_id._get_api_client()

        data = self._prepare_stock_price_data()
        if not data:
            _logger.debug("No HB stock/price changes for %s", self.display_name)
            return

        try:
            client.update_listing_inventory([data])
            self.last_sent_quantity = data["AvailableStock"]
            self.last_sent_price = data["Price"]
            self.last_sync_date = fields.Datetime.now()
            _logger.info(
                "Synced HB stock/price for %s: qty=%d, price=%.2f",
                self.display_name,
                data["AvailableStock"],
                data["Price"],
            )
        except HepsiburadaAPIError as e:
            _logger.error(
                "Failed to sync HB stock/price for %s: %s",
                self.display_name,
                str(e),
            )
            raise

    def action_set_draft(self):
        """Reset binding to draft state."""
        self.ensure_one()
        self.sync_state = "draft"
        self.sync_error = False
        return True
