# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import fields, models

DEFAULT_IMAGE_URL = "https://www.altinkaya.com/web/image/product.brand/1/logo"


class MarketplaceProductBinding(models.AbstractModel):
    _name = "marketplace.product.binding"
    _description = "Abstract Marketplace Product Binding"
    _order = "create_date desc"

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

    # VAT
    vat_rate = fields.Float(
        string="VAT Rate (%)",
        default=20.0,
    )

    def action_set_draft(self):
        """Reset binding to draft state."""
        self.ensure_one()
        self.sync_state = "draft"
        self.sync_error = False
        return True

    def _get_image_url(self, product):
        """Get HTTPS image URL for the product, with fallback to default.

        Args:
            product: product.product record

        Returns:
            Image URL string
        """
        if product.image_url:
            url = product.image_url
            if url.startswith("https://"):
                return url
            if url.startswith("http://"):
                return url.replace("http://", "https://", 1)

        base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url")
        if base_url and product.image_1920:
            return f"{base_url}/web/image/product.product/{product.id}/image_1920"

        return DEFAULT_IMAGE_URL

    def _get_description(self, product):
        """Get product description with fallback chain.

        Args:
            product: product.product record

        Returns:
            Description string
        """
        if hasattr(product, "public_description") and product.public_description:
            return product.public_description[:30000]
        if product.description_sale:
            return product.description_sale[:30000]
        return product.name[:30000]
