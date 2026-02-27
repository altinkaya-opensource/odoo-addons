# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import json
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from .trendyol_request import TrendyolAPIError

_logger = logging.getLogger(__name__)


class TrendyolProductBinding(models.Model):
    _name = "trendyol.product.binding"
    _description = "Trendyol Product Binding"
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
        "trendyol.backend",
        required=True,
        ondelete="cascade",
        index=True,
    )

    # Trendyol identifiers
    trendyol_barcode = fields.Char(
        required=True,
        index=True,
        help="Barcode used in Trendyol (usually same as Odoo barcode)",
    )
    trendyol_product_id = fields.Char(
        string="Trendyol Product ID",
        readonly=True,
        index=True,
        help="Product ID assigned by Trendyol after approval",
    )
    trendyol_stock_code = fields.Char(
        string="Stock Code",
        help="Your internal stock/SKU code",
    )

    # Mappings
    trendyol_category_id = fields.Many2one(
        "trendyol.category",
        required=True,
        domain="[('backend_id', '=', backend_id), ('is_leaf', '=', True)]",
    )
    trendyol_brand_id = fields.Many2one(
        "trendyol.brand",
        required=True,
        domain="[('backend_id', '=', backend_id)]",
    )

    # Attributes (stored as JSON)
    trendyol_attributes = fields.Text(
        help="JSON array of category attributes",
    )

    # Sync state
    sync_state = fields.Selection(
        [
            ("draft", "Draft"),
            ("pending", "Pending Approval"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
            ("error", "Error"),
        ],
        default="draft",
        required=True,
        index=True,
    )
    sync_error = fields.Text(
        readonly=True,
    )
    last_sync_date = fields.Datetime(
        readonly=True,
    )

    # Prices
    trendyol_list_price = fields.Float(
        string="List Price",
        digits="Product Price",
        compute="_compute_prices",
        store=True,
        help="List price in TRY from configured pricelist",
    )
    trendyol_sale_price = fields.Float(
        string="Sale Price",
        digits="Product Price",
        help="Sale price in TRY (if different from list price)",
    )

    # Stock
    trendyol_quantity = fields.Float(
        compute="_compute_trendyol_quantity",
        help="Available quantity for Trendyol",
    )
    last_sent_quantity = fields.Float(
        readonly=True,
    )
    last_sent_price = fields.Float(
        readonly=True,
    )

    # VAT
    vat_rate = fields.Float(
        string="VAT Rate (%)",
        default=20.0,
    )

    _sql_constraints = [
        (
            "barcode_backend_uniq",
            "unique(trendyol_barcode, backend_id)",
            "Barcode must be unique per backend!",
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
                binding.trendyol_list_price = 0.0
                continue

            pricelist = binding.backend_id.pricelist_id
            price = pricelist._get_product_price(
                binding.odoo_id,
                quantity=1.0,
                partner=False,
            )
            binding.trendyol_list_price = price

    @api.depends("odoo_id", "backend_id", "backend_id.warehouse_ids")
    def _compute_trendyol_quantity(self):
        for binding in self:
            if not binding.backend_id.warehouse_ids or not binding.odoo_id:
                binding.trendyol_quantity = 0.0
                continue

            # Sum available qty across all warehouse locations
            total_qty = 0.0
            for warehouse in binding.backend_id.warehouse_ids:
                total_qty += binding.odoo_id.with_context(
                    location=warehouse.lot_stock_id.id
                ).free_qty
            binding.trendyol_quantity = total_qty

    @api.constrains("trendyol_barcode")
    def _check_barcode(self):
        for binding in self:
            if not binding.trendyol_barcode:
                raise ValidationError(_("Trendyol barcode is required."))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            # Default barcode from product if not set
            if not vals.get("trendyol_barcode") and vals.get("odoo_id"):
                product = self.env["product.product"].browse(vals["odoo_id"])
                vals["trendyol_barcode"] = product.barcode or product.default_code
            # Default stock code
            if not vals.get("trendyol_stock_code") and vals.get("odoo_id"):
                product = self.env["product.product"].browse(vals["odoo_id"])
                vals["trendyol_stock_code"] = product.default_code
        return super().create(vals_list)

    def _prepare_product_data(self):
        """Prepare product data for Trendyol API.

        Returns:
            Dict with product data for API
        """
        self.ensure_one()

        if not self.trendyol_category_id:
            raise UserError(
                _("Trendyol category is required for product %s") % self.display_name
            )
        if not self.trendyol_brand_id:
            raise UserError(
                _("Trendyol brand is required for product %s") % self.display_name
            )

        # Get image URL
        image_url = self._get_image_url()
        if not image_url:
            raise UserError(
                _("Product image URL is required for %s") % self.display_name
            )

        # Calculate prices
        list_price = self.trendyol_list_price
        sale_price = self.trendyol_sale_price or list_price

        if not sale_price or sale_price <= 0:
            _logger.warning(
                "Product price must be greater than 0 for product %s", self.display_name
            )
            return None

        data = {
            "barcode": self.trendyol_barcode,
            "title": self.name[:100],  # Max 100 chars
            "productMainId": self.trendyol_stock_code
            or self.default_code
            or self.trendyol_barcode,
            "brandId": self.trendyol_brand_id.trendyol_id,
            "categoryId": self.trendyol_category_id.trendyol_id,
            "quantity": int(max(0, self.trendyol_quantity)),
            "stockCode": self.trendyol_stock_code
            or self.default_code
            or self.trendyol_barcode,
            "dimensionalWeight": self._calculate_dimensional_weight(),
            "description": self._get_description(),
            "currencyType": "TRY",
            "listPrice": list_price,
            "salePrice": sale_price,
            "vatRate": int(self.vat_rate),
            "cargoCompanyId": self._get_cargo_company_id(),
            "images": [{"url": image_url}],
            "attributes": self._get_attributes(),
        }

        return data

    def _get_image_url(self):
        """Get HTTPS image URL for the product.

        Returns:
            Image URL string or None
        """
        # Try to get public URL from product
        # This would typically be set up to serve images via HTTPS
        if self.odoo_id.image_url:
            url = self.odoo_id.image_url
            if url.startswith("https://"):
                return url
            if url.startswith("http://"):
                return url.replace("http://", "https://", 1)

        # Check if there's a website configured
        base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url")
        if base_url and self.odoo_id.image_1920:
            # This assumes images are accessible via web
            return f"{base_url}/web/image/product.product/{self.odoo_id.id}/image_1920"

        # return None
        return "https://www.altinkaya.com/web/image/product.brand/1/logo"
        # export sırasında hata vermesin diye default bir logo döndürdüm

    def _get_description(self):
        """Get product description for Trendyol.

        Returns:
            HTML description string
        """
        # Priority: public_description > description_sale > name
        product = self.odoo_id
        if hasattr(product, "public_description") and product.public_description:
            return product.public_description[:30000]
        if product.description_sale:
            return product.description_sale[:30000]
        return product.name[:30000]

    def _calculate_dimensional_weight(self):
        """Calculate dimensional weight for shipping.

        Returns:
            Dimensional weight as integer
        """
        product = self.odoo_id
        if product.volume and product.volume > 0:
            # Dimensional weight = volume (m3) * 1,000,000 / 5000
            # Convert from m3 to cm3 and apply divisor
            dim_weight = (product.volume * 1000000) / 5000
            return max(1, int(dim_weight))

        # Default to actual weight if available
        if product.weight and product.weight > 0:
            return max(1, int(product.weight * 1000))  # Convert kg to g

        return 1  # Minimum weight

    def _get_cargo_company_id(self):
        """Get cargo company ID for Trendyol.

        Returns:
            Cargo company ID or default
        """
        # Would need mapping to Trendyol cargo company IDs
        # Return None to use Trendyol's default
        return None

    def _get_attributes(self):
        """Get category attributes for Trendyol.

        Returns:
            List of attribute dicts
        """
        if not self.trendyol_attributes:
            return []

        try:
            return json.loads(self.trendyol_attributes)
        except (json.JSONDecodeError, TypeError):
            return []

    def _prepare_stock_price_data(self):
        """Prepare stock/price update data for Trendyol API.

        Returns:
            Dict with stock/price data or None if no changes
        """
        self.ensure_one()

        quantity = int(max(0, self.trendyol_quantity))
        list_price = self.trendyol_list_price
        sale_price = self.trendyol_sale_price or list_price

        # Check if anything changed
        if quantity == self.last_sent_quantity and sale_price == self.last_sent_price:
            return None

        return {
            "barcode": self.trendyol_barcode,
            "quantity": quantity,
            "salePrice": sale_price,
            "listPrice": list_price,
        }

    def action_export_to_trendyol(self):
        """Export product to Trendyol."""
        self.ensure_one()
        self.with_delay(
            channel="root.trendyol.product",
            description=_("Export product to Trendyol: %s") % self.display_name,
        )._export_to_trendyol()
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

    def _export_to_trendyol(self):
        """Export product to Trendyol API."""
        self.ensure_one()
        client = self.backend_id._get_api_client()
        BatchRequest = self.env["trendyol.batch.request"]

        try:
            data = self._prepare_product_data()
            result = client.create_products([data])

            batch_id = result.get("batchRequestId")
            if batch_id:
                BatchRequest.create(
                    {
                        "backend_id": self.backend_id.id,
                        "batch_request_id": batch_id,
                        "request_type": "product_create",
                        "state": "pending",
                        "total_items": 1,
                        "product_binding_ids": [(4, self.id)],
                    }
                )
                self.sync_state = "pending"
                self.last_sync_date = fields.Datetime.now()
                _logger.info(
                    "Exported product %s, batch: %s",
                    self.display_name,
                    batch_id,
                )
        except TrendyolAPIError as e:
            self.sync_state = "error"
            self.sync_error = str(e)
            _logger.error("Failed to export product %s: %s", self.display_name, str(e))
            raise
        except UserError as e:
            self.sync_state = "error"
            self.sync_error = str(e)
            raise

    def action_update_in_trendyol(self):
        """Update product in Trendyol."""
        self.ensure_one()
        if self.sync_state != "approved":
            raise UserError(_("Only approved products can be updated."))

        self.with_delay(
            channel="root.trendyol.product",
            description=_("Update product in Trendyol: %s") % self.display_name,
        )._update_in_trendyol()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Update Started"),
                "message": _("Product update has been queued."),
                "type": "info",
                "sticky": False,
            },
        }

    def _update_in_trendyol(self):
        """Update product in Trendyol API."""
        self.ensure_one()
        client = self.backend_id._get_api_client()
        BatchRequest = self.env["trendyol.batch.request"]

        try:
            data = self._prepare_product_data()
            result = client.update_products([data])

            batch_id = result.get("batchRequestId")
            if batch_id:
                BatchRequest.create(
                    {
                        "backend_id": self.backend_id.id,
                        "batch_request_id": batch_id,
                        "request_type": "product_update",
                        "state": "pending",
                        "total_items": 1,
                        "product_binding_ids": [(4, self.id)],
                    }
                )
                self.last_sync_date = fields.Datetime.now()
                _logger.info(
                    "Updated product %s, batch: %s",
                    self.display_name,
                    batch_id,
                )
        except TrendyolAPIError as e:
            self.sync_error = str(e)
            _logger.error("Failed to update product %s: %s", self.display_name, str(e))
            raise

    def action_sync_stock_price(self):
        """Sync stock and price for this product."""
        self.ensure_one()
        if self.sync_state != "approved":
            raise UserError(_("Only approved products can have stock/price synced."))

        self.with_delay(
            channel="root.trendyol.stock",
            description=_("Sync stock/price: %s") % self.display_name,
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
        """Sync stock and price to Trendyol API."""
        self.ensure_one()
        client = self.backend_id._get_api_client()

        data = self._prepare_stock_price_data()
        if not data:
            _logger.debug("No stock/price changes for %s", self.display_name)
            return

        try:
            client.update_price_and_inventory([data])
            self.last_sent_quantity = data["quantity"]
            self.last_sent_price = data["salePrice"]
            self.last_sync_date = fields.Datetime.now()
            _logger.info(
                "Synced stock/price for %s: qty=%d, price=%.2f",
                self.display_name,
                data["quantity"],
                data["salePrice"],
            )
        except TrendyolAPIError as e:
            _logger.error(
                "Failed to sync stock/price for %s: %s",
                self.display_name,
                str(e),
            )
            raise

    def action_view_in_trendyol(self):
        """Open product in Trendyol seller panel (if approved)."""
        self.ensure_one()
        if not self.trendyol_product_id:
            raise UserError(_("Product not yet approved in Trendyol."))

        # Trendyol seller panel URL
        base_url = "https://partner.trendyol.com"
        url = f"{base_url}/product/detail/{self.trendyol_product_id}"

        return {
            "type": "ir.actions.act_url",
            "url": url,
            "target": "new",
        }

    def action_set_draft(self):
        """Reset binding to draft state."""
        self.ensure_one()
        self.sync_state = "draft"
        self.sync_error = False
        return True
