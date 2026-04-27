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
    _inherit = ["marketplace.product.binding.mixin"]
    _inherits = {"product.product": "odoo_id"}
    _order = "create_date desc"

    backend_id = fields.Many2one(
        "trendyol.backend",
        required=True,
        ondelete="cascade",
        index=True,
    )

    trendyol_barcode = fields.Char(
        required=True,
        index=True,
        help="Barcode used in Trendyol (max 40 chars, [.-_] and Turkish chars allowed)",
    )
    trendyol_product_id = fields.Char(
        string="Trendyol Product ID",
        readonly=True,
        index=True,
        help="Product ID assigned by Trendyol after approval",
    )
    trendyol_stock_code = fields.Char(
        string="Stock Code",
        help="Internal stock/SKU code, sent as stockCode in payload",
    )
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
    trendyol_attributes = fields.Text(help="JSON array of Trendyol category attributes")

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

    @api.constrains("trendyol_barcode")
    def _check_barcode(self):
        for binding in self:
            if not binding.trendyol_barcode:
                raise ValidationError(_("Trendyol barcode is required."))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("trendyol_barcode") and vals.get("odoo_id"):
                product = self.env["product.product"].browse(vals["odoo_id"])
                vals["trendyol_barcode"] = product.barcode or product.default_code
            if not vals.get("trendyol_stock_code") and vals.get("odoo_id"):
                product = self.env["product.product"].browse(vals["odoo_id"])
                vals["trendyol_stock_code"] = product.default_code
        return super().create(vals_list)

    # --- Marketplace mixin overrides ---------------------------------------

    def _marketplace_product_label(self):
        return _("Trendyol product")

    def _marketplace_queue_channel(self):
        return "root.trendyol.product"

    def _prepare_marketplace_payload(self):
        """Build the Trendyol product create/update payload.

        Per docs at trendyol-docs/pages/v2.0/docs/product-create-createproducts.md.
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

        image_urls = self._get_marketplace_image_urls(limit=8)
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

        backend = self.backend_id
        template = self.odoo_id.product_tmpl_id

        data = {
            "barcode": self.trendyol_barcode,
            "title": self.odoo_id.name[:100],
            "productMainId": self._get_variant_group_id(),
            "brandId": self.trendyol_brand_id.trendyol_id,
            "categoryId": self.trendyol_category_id.trendyol_id,
            "quantity": int(max(0, self.marketplace_quantity)),
            "stockCode": self.trendyol_stock_code
            or self.odoo_id.default_code
            or self.trendyol_barcode,
            "dimensionalWeight": self._get_marketplace_dimensional_weight(),
            "description": self._get_marketplace_description(max_chars=30000),
            "currencyType": "TRY",
            "listPrice": list_price,
            "salePrice": sale_price,
            "vatRate": int(self.vat_rate),
            "cargoCompanyId": self._get_cargo_company_id(),
            "images": [{"url": url} for url in image_urls],
            "attributes": self._get_attributes(),
        }

        if backend.default_shipment_address_id:
            data["shipmentAddressId"] = backend.default_shipment_address_id
        if backend.default_returning_address_id:
            data["returningAddressId"] = backend.default_returning_address_id
        if backend.default_delivery_duration:
            data["deliveryOption"] = {
                "deliveryDuration": backend.default_delivery_duration,
            }
            if backend.default_fast_delivery_type:
                data["deliveryOption"]["fastDeliveryType"] = (
                    backend.default_fast_delivery_type
                )
        if template.marketplace_lot_number:
            data["lotNumber"] = template.marketplace_lot_number

        return data

    def _prepare_stock_price_payload(self):
        self.ensure_one()
        quantity = int(max(0, self.marketplace_quantity))
        list_price = self.marketplace_list_price
        sale_price = self.marketplace_sale_price or list_price
        if quantity == self.last_sent_quantity and sale_price == self.last_sent_price:
            return None
        return {
            "barcode": self.trendyol_barcode,
            "quantity": quantity,
            "salePrice": sale_price,
            "listPrice": list_price,
        }

    def _get_cargo_company_id(self):
        """Trendyol cargo company id, from category mapping or backend default."""
        self.ensure_one()
        category = self.trendyol_category_id
        if category and category.cargo_company_id:
            return category.cargo_company_id
        return self.backend_id.default_cargo_company_external_id or None

    def _get_attributes(self):
        if not self.trendyol_attributes:
            return []
        try:
            return json.loads(self.trendyol_attributes)
        except (json.JSONDecodeError, TypeError):
            return []

    # --- Concrete export/update/sync methods --------------------------------

    def _export(self):
        self.ensure_one()
        client = self.backend_id._get_api_client()
        BatchRequest = self.env["trendyol.batch.request"]
        try:
            data = self._prepare_marketplace_payload()
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
                self.write(
                    {
                        "sync_state": "pending",
                        "last_sync_date": fields.Datetime.now(),
                    }
                )
                _logger.info(
                    "Exported product %s, batch: %s",
                    self.display_name,
                    batch_id,
                )
        except TrendyolAPIError as e:
            self.write({"sync_state": "error", "sync_error": str(e)})
            _logger.error("Failed to export product %s: %s", self.display_name, str(e))
            raise
        except UserError as e:
            self.write({"sync_state": "error", "sync_error": str(e)})
            raise

    def _update(self):
        self.ensure_one()
        client = self.backend_id._get_api_client()
        BatchRequest = self.env["trendyol.batch.request"]
        try:
            data = self._prepare_marketplace_payload()
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

    def _sync_stock_price(self):
        self.ensure_one()
        client = self.backend_id._get_api_client()
        data = self._prepare_stock_price_payload()
        if not data:
            _logger.debug("No stock/price changes for %s", self.display_name)
            return
        try:
            client.update_price_and_inventory([data])
            self.write(
                {
                    "last_sent_quantity": data["quantity"],
                    "last_sent_price": data["salePrice"],
                    "last_sync_date": fields.Datetime.now(),
                }
            )
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

    # --- Backwards-compatible action aliases --------------------------------
    # Existing views/buttons reference these names; keep them working.

    def action_export_to_trendyol(self):
        return self.action_export()

    def action_update_in_trendyol(self):
        return self.action_update()

    def action_view_in_trendyol(self):
        self.ensure_one()
        if not self.trendyol_product_id:
            raise UserError(_("Product not yet approved in Trendyol."))
        return {
            "type": "ir.actions.act_url",
            "url": f"https://partner.trendyol.com/product/detail/{self.trendyol_product_id}",
            "target": "new",
        }
