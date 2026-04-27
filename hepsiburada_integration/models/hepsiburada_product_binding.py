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
    _inherit = ["marketplace.product.binding.mixin"]
    _inherits = {"product.product": "odoo_id"}
    _order = "create_date desc"

    backend_id = fields.Many2one(
        "hepsiburada.backend",
        required=True,
        ondelete="cascade",
        index=True,
    )

    merchant_sku = fields.Char(
        string="Merchant SKU",
        required=True,
        index=True,
        help="Internal SKU sent to Hepsiburada (must be unique per merchant)",
    )
    hepsiburada_sku = fields.Char(
        string="Hepsiburada SKU",
        readonly=True,
        index=True,
        help="HB SKU assigned after the catalog upload is approved",
    )
    variant_group_id = fields.Char(
        string="Variant Group ID",
        help="Common identifier shared by sibling variants (HB VaryantGroupID)",
    )
    hepsiburada_category_id = fields.Many2one(
        "hepsiburada.category",
        required=True,
        domain="[('backend_id', '=', backend_id), ('is_leaf', '=', True)]",
    )
    hepsiburada_brand_id = fields.Many2one(
        "hepsiburada.brand",
        domain="[('backend_id', '=', backend_id)]",
    )

    # Listing fields
    dispatch_time = fields.Integer(
        string="Dispatch Time (days)",
        default=1,
        help="Number of days from order to dispatch",
    )
    cargo_company_1 = fields.Char()
    cargo_company_2 = fields.Char()
    cargo_company_3 = fields.Char()
    shipping_address_label = fields.Char()
    claim_address_label = fields.Char()
    shipping_profile_name = fields.Char()
    maximum_purchasable_quantity = fields.Integer(default=0)
    minimum_purchasable_quantity = fields.Integer(default=0)
    is_listing_active = fields.Boolean(
        default=True,
        help="Listing is currently active on Hepsiburada",
    )
    customization_text_type = fields.Char()
    customization_text_length = fields.Integer()
    has_installation = fields.Boolean()

    tracking_id = fields.Char(
        string="Catalog Upload Tracking ID",
        readonly=True,
        index=True,
        help="trackingId returned by /api/products/import",
    )
    attributes = fields.Text(
        help="JSON object holding category-specific attribute values "
        "(merged into the catalog upload payload as the `attributes` block)",
    )
    warranty_months = fields.Integer(
        string="Warranty (Months)",
        default=24,
        help="Override the template-level marketplace_warranty_months",
    )

    _sql_constraints = [
        (
            "merchant_sku_backend_uniq",
            "unique(merchant_sku, backend_id)",
            "Merchant SKU must be unique per backend!",
        ),
        (
            "product_backend_uniq",
            "unique(odoo_id, backend_id)",
            "Product can only be bound once per backend!",
        ),
    ]

    @api.constrains("merchant_sku")
    def _check_merchant_sku(self):
        for binding in self:
            if not binding.merchant_sku:
                raise ValidationError(_("Hepsiburada merchant SKU is required."))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("odoo_id"):
                product = self.env["product.product"].browse(vals["odoo_id"])
                if not vals.get("merchant_sku"):
                    vals["merchant_sku"] = product.default_code or product.barcode
                if not vals.get("variant_group_id"):
                    vals["variant_group_id"] = (
                        product.product_tmpl_id.default_code
                        or f"TMPL-{product.product_tmpl_id.id}"
                    )
        return super().create(vals_list)

    # --- Marketplace mixin overrides ---------------------------------------

    def _marketplace_product_label(self):
        return _("Hepsiburada product")

    def _marketplace_queue_channel(self):
        return "root.hepsiburada.product"

    def _get_attributes(self):
        if not self.attributes:
            return {}
        try:
            return json.loads(self.attributes)
        except (json.JSONDecodeError, TypeError):
            return {}

    def _prepare_marketplace_payload(self):
        """Build a single product entry for the catalog upload JSON file.

        Per docs/reference.md (mpop /api/products/import):
        - Top-level: categoryId, merchant, attributes
        - attributes block: merchantSku, VaryantGroupID, Barcode, UrunAdi,
          UrunAciklamasi, Marka, GarantiSuresi, kg, tax_vat_rate, price,
          stock, Image1..Image5, Video1, plus dynamic category attributes.
        """
        self.ensure_one()
        product = self.odoo_id
        template = product.product_tmpl_id

        if not self.hepsiburada_category_id:
            raise UserError(
                _("Hepsiburada category is required for product %s") % self.display_name
            )
        if not self.hepsiburada_brand_id and not template.product_brand_id:
            raise UserError(
                _("Hepsiburada brand is required for product %s") % self.display_name
            )

        image_urls = self._get_marketplace_image_urls(limit=5)
        if not image_urls:
            raise UserError(
                _("At least one image URL is required for %s") % self.display_name
            )

        list_price = self.marketplace_list_price
        sale_price = self.marketplace_sale_price or list_price
        if not sale_price or sale_price <= 0:
            raise UserError(
                _("Sale price must be greater than 0 for %s") % self.display_name
            )

        warranty = self.warranty_months or template.marketplace_warranty_months or 24

        attrs = {
            "merchantSku": self.merchant_sku,
            "VaryantGroupID": self.variant_group_id or self._get_variant_group_id(),
            "Barcode": product.barcode or self.merchant_sku,
            "UrunAdi": product.name[:255],
            "UrunAciklamasi": self._get_marketplace_description(max_chars=30000),
            "Marka": (
                self.hepsiburada_brand_id.name
                if self.hepsiburada_brand_id
                else (
                    template.product_brand_id.name if template.product_brand_id else ""
                )
            ),
            "GarantiSuresi": warranty,
            "kg": self._get_marketplace_dimensional_weight(),
            "tax_vat_rate": int(self.vat_rate),
            "price": sale_price,
            "stock": int(max(0, self.marketplace_quantity)),
        }
        for index, url in enumerate(image_urls, start=1):
            attrs[f"Image{index}"] = url
        if template.marketplace_video_url:
            attrs["Video1"] = template.marketplace_video_url

        # Merge dynamic per-category attributes
        attrs.update(self._get_attributes())

        return {
            "categoryId": self.hepsiburada_category_id.hepsiburada_category_id,
            "merchant": self.backend_id.merchant_id,
            "attributes": attrs,
        }

    def _prepare_listing_payload(self):
        """Build the InventoryUploadRequestModel for /listings/inventory-uploads."""
        self.ensure_one()
        list_price = self.marketplace_list_price
        sale_price = self.marketplace_sale_price or list_price
        payload = {
            "hepsiburadaSku": self.hepsiburada_sku or "",
            "merchantSku": self.merchant_sku,
            "price": sale_price,
            "availableStock": int(max(0, self.marketplace_quantity)),
            "dispatchTime": self.dispatch_time or self.backend_id.default_dispatch_time,
            "maximumPurchasableQuantity": self.maximum_purchasable_quantity,
        }
        if self.minimum_purchasable_quantity:
            payload["minimumPurchasableQuantity"] = self.minimum_purchasable_quantity
        if self.cargo_company_1 or self.backend_id.default_cargo_company_1:
            payload["cargoCompany1"] = (
                self.cargo_company_1 or self.backend_id.default_cargo_company_1
            )
        if self.cargo_company_2 or self.backend_id.default_cargo_company_2:
            payload["cargoCompany2"] = (
                self.cargo_company_2 or self.backend_id.default_cargo_company_2
            )
        if self.cargo_company_3 or self.backend_id.default_cargo_company_3:
            payload["cargoCompany3"] = (
                self.cargo_company_3 or self.backend_id.default_cargo_company_3
            )
        if (
            self.shipping_address_label
            or self.backend_id.default_shipping_address_label
        ):
            payload["shippingAddressLabel"] = (
                self.shipping_address_label
                or self.backend_id.default_shipping_address_label
            )
        if self.claim_address_label or self.backend_id.default_claim_address_label:
            payload["claimAddressLabel"] = (
                self.claim_address_label or self.backend_id.default_claim_address_label
            )
        if self.shipping_profile_name or self.backend_id.default_shipping_profile_name:
            payload["shippingProfileName"] = (
                self.shipping_profile_name
                or self.backend_id.default_shipping_profile_name
            )
        if self.customization_text_type:
            payload["customizationTextType"] = self.customization_text_type
        if self.customization_text_length:
            payload["customizationTextLength"] = self.customization_text_length
        if self.has_installation:
            payload["hasInstallation"] = True
        return payload

    def _prepare_stock_price_payload(self):
        """Slim payload used by the stock + price uploads (delta only)."""
        self.ensure_one()
        quantity = int(max(0, self.marketplace_quantity))
        list_price = self.marketplace_list_price
        sale_price = self.marketplace_sale_price or list_price
        if quantity == self.last_sent_quantity and sale_price == self.last_sent_price:
            return None
        return {
            "hepsiburadaSku": self.hepsiburada_sku or "",
            "merchantSku": self.merchant_sku,
            "availableStock": quantity,
            "price": sale_price,
        }

    # --- Concrete export/update/sync methods --------------------------------

    def _export(self):
        """Submit the product to the HB catalog (/api/products/import)."""
        self.ensure_one()
        client = self.backend_id._get_api_client()
        BatchRequest = self.env["hepsiburada.batch.request"]
        try:
            payload = self._prepare_marketplace_payload()
            result = client.import_product([payload])
            tracking_id = result.get("trackingId") or result.get("data", {}).get(
                "trackingId"
            )
            if not tracking_id:
                raise UserError(
                    _("Hepsiburada returned no trackingId. Raw response: %s") % result
                )
            BatchRequest.create(
                {
                    "backend_id": self.backend_id.id,
                    "batch_request_id": tracking_id,
                    "request_type": "product_create",
                    "state": "pending",
                    "total_items": 1,
                    "product_binding_ids": [(4, self.id)],
                }
            )
            self.write(
                {
                    "tracking_id": tracking_id,
                    "sync_state": "pending",
                    "last_sync_date": fields.Datetime.now(),
                }
            )
            _logger.info(
                "HB catalog upload submitted for %s (trackingId=%s)",
                self.display_name,
                tracking_id,
            )
        except HepsiburadaAPIError as e:
            self.write({"sync_state": "error", "sync_error": str(e)})
            _logger.error("Failed to export HB product %s: %s", self.display_name, e)
            raise
        except UserError as e:
            self.write({"sync_state": "error", "sync_error": str(e)})
            raise

    def _update(self):
        """Push a full listing update via /listings/inventory-uploads."""
        self.ensure_one()
        client = self.backend_id._get_api_client()
        try:
            payload = self._prepare_listing_payload()
            client.inventory_uploads([payload])
            self.last_sync_date = fields.Datetime.now()
            _logger.info("HB listing updated for %s", self.display_name)
        except HepsiburadaAPIError as e:
            self.sync_error = str(e)
            _logger.error("Failed to update HB listing %s: %s", self.display_name, e)
            raise

    def _sync_stock_price(self):
        """Push delta stock+price via the dedicated upload endpoints."""
        self.ensure_one()
        client = self.backend_id._get_api_client()
        data = self._prepare_stock_price_payload()
        if not data:
            _logger.debug("No stock/price changes for HB %s", self.display_name)
            return
        try:
            client.stock_uploads(
                [
                    {
                        "hepsiburadaSku": data["hepsiburadaSku"],
                        "merchantSku": data["merchantSku"],
                        "availableStock": data["availableStock"],
                    }
                ]
            )
            client.price_uploads(
                [
                    {
                        "hepsiburadaSku": data["hepsiburadaSku"],
                        "merchantSku": data["merchantSku"],
                        "price": data["price"],
                    }
                ]
            )
            self.write(
                {
                    "last_sent_quantity": data["availableStock"],
                    "last_sent_price": data["price"],
                    "last_sync_date": fields.Datetime.now(),
                }
            )
            _logger.info(
                "Synced HB stock/price for %s: stock=%d price=%.2f",
                self.display_name,
                data["availableStock"],
                data["price"],
            )
        except HepsiburadaAPIError as e:
            _logger.error(
                "Failed to sync HB stock/price for %s: %s", self.display_name, e
            )
            raise

    def action_activate_listing(self):
        self.ensure_one()
        if not self.hepsiburada_sku:
            raise UserError(_("Listing not yet approved on Hepsiburada."))
        client = self.backend_id._get_api_client()
        client.activate_sku(self.hepsiburada_sku)
        self.is_listing_active = True
        return True

    def action_deactivate_listing(self):
        self.ensure_one()
        if not self.hepsiburada_sku:
            raise UserError(_("Listing not yet approved on Hepsiburada."))
        client = self.backend_id._get_api_client()
        client.deactivate_sku(self.hepsiburada_sku)
        self.is_listing_active = False
        return True
