# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class MarketplaceProductBindingMixin(models.AbstractModel):
    """Abstract mixin for marketplace product bindings.

    Concrete child models declare:
        _name = "<marketplace>.product.binding"
        _inherit = ["marketplace.product.binding.mixin"]
        _inherits = {"product.product": "odoo_id"}
        backend_id = fields.Many2one("<marketplace>.backend", ...)

    Children should override:
        _prepare_marketplace_payload() -- main product create/update payload
        _prepare_stock_price_payload() -- slim stock+price payload
        _export() / _update() / _sync_stock_price() -- API calls
    """

    _name = "marketplace.product.binding.mixin"
    _description = "Marketplace Product Binding Mixin"

    odoo_id = fields.Many2one(
        "product.product",
        string="Odoo Product",
        required=True,
        ondelete="cascade",
        index=True,
    )

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
    sync_error = fields.Text(readonly=True)
    last_sync_date = fields.Datetime(readonly=True)

    marketplace_quantity = fields.Float(
        compute="_compute_marketplace_quantity",
        digits="Product Unit of Measure",
        help="Available quantity for the marketplace (sum across backend warehouses)",
    )
    marketplace_list_price = fields.Float(
        compute="_compute_marketplace_prices",
        digits="Product Price",
        store=True,
    )
    marketplace_sale_price = fields.Float(
        digits="Product Price",
        help="Sale price (defaults to list price when blank)",
    )

    last_sent_quantity = fields.Float(readonly=True)
    last_sent_price = fields.Float(readonly=True)

    vat_rate = fields.Float(
        string="VAT Rate (%)",
        default=20.0,
    )

    @api.depends("odoo_id", "backend_id", "backend_id.pricelist_id")
    def _compute_marketplace_prices(self):
        for binding in self:
            pricelist = binding.backend_id.pricelist_id
            if not pricelist or not binding.odoo_id:
                binding.marketplace_list_price = 0.0
                continue
            binding.marketplace_list_price = pricelist._get_product_price(
                binding.odoo_id,
                quantity=1.0,
                partner=False,
            )

    @api.depends("odoo_id", "backend_id", "backend_id.warehouse_ids")
    def _compute_marketplace_quantity(self):
        for binding in self:
            warehouses = binding.backend_id.warehouse_ids
            if not warehouses or not binding.odoo_id:
                binding.marketplace_quantity = 0.0
                continue
            total = 0.0
            for warehouse in warehouses:
                total += binding.odoo_id.with_context(
                    location=warehouse.lot_stock_id.id
                ).free_qty
            binding.marketplace_quantity = total

    # --- Hook methods (override in children) --------------------------------

    def _prepare_marketplace_payload(self):
        """Build the create/update product payload for the marketplace API."""
        raise NotImplementedError

    def _prepare_stock_price_payload(self):
        """Build the slim stock+price payload. Return None if nothing changed."""
        raise NotImplementedError

    def _export(self):
        """Send the product to the marketplace (create)."""
        raise NotImplementedError

    def _update(self):
        """Update the product on the marketplace."""
        raise NotImplementedError

    def _sync_stock_price(self):
        """Push stock and price changes."""
        raise NotImplementedError

    def _marketplace_queue_channel(self):
        return self.backend_id._marketplace_queue_channel()

    def _marketplace_product_label(self):
        return _("Marketplace product")

    # --- Reusable helpers ---------------------------------------------------

    def _get_marketplace_image_urls(self, limit=8):
        """Return ordered list of public image URLs for this binding.

        Pulls from base_multi_image image_ids (filtered by is_published, sorted
        by sequence). Each base_multi_image.image record exposes an `image_url`
        Char added by marketplace_integration_base. Falls back to
        product.product.image_url for the first slot when no multi-image
        records have an URL set.
        """
        self.ensure_one()
        urls = []
        product = self.odoo_id

        image_records = getattr(product, "image_ids", False) or getattr(
            product.product_tmpl_id, "image_ids", False
        )
        if image_records:
            published = image_records.filtered(
                lambda i: i.is_published and i.image_url
            ).sorted("sequence")
            for img in published[:limit]:
                urls.append(self._normalize_marketplace_url(img.image_url))

        if not urls and product.image_url:
            urls.append(self._normalize_marketplace_url(product.image_url))

        return [url for url in urls if url]

    @staticmethod
    def _normalize_marketplace_url(url):
        if not url:
            return None
        if url.startswith("http://"):
            return "https://" + url[len("http://") :]
        return url

    def _get_marketplace_description(self, max_chars=30000):
        """Pick the best description in the order: public_description ->
        description_sale -> name. Truncate to ``max_chars`` characters.
        """
        self.ensure_one()
        product = self.odoo_id
        text = (
            getattr(product, "public_description", False)
            or product.description_sale
            or product.name
            or ""
        )
        return text[:max_chars]

    def _get_marketplace_dimensional_weight(self):
        """Return the desi (dimensional weight) for shipping calculation.

        Priority: product.template.marketplace_dimensional_weight,
        then volume-based, then physical weight, with a minimum of 1.
        """
        self.ensure_one()
        product = self.odoo_id
        template_dw = getattr(
            product.product_tmpl_id, "marketplace_dimensional_weight", 0.0
        )
        if template_dw:
            return max(1, int(template_dw))
        if product.volume and product.volume > 0:
            return max(1, int((product.volume * 1000000) / 5000))
        if product.weight and product.weight > 0:
            return max(1, int(product.weight * 1000))
        return 1

    def _get_variant_group_id(self):
        """Identifier shared by variants of the same template.

        Used as Trendyol's productMainId / Hepsiburada's VaryantGroupID.
        """
        self.ensure_one()
        template = self.odoo_id.product_tmpl_id
        return template.default_code or f"TMPL-{template.id}"

    # --- Action wrappers ----------------------------------------------------

    def _action_queue_method(self, method_name, description, channel=None):
        """Queue ``method_name`` and return a notification action."""
        self.ensure_one()
        getattr(
            self.with_delay(
                channel=channel or self._marketplace_queue_channel(),
                description=description,
            ),
            method_name,
        )()
        return self.backend_id._marketplace_notification(
            _("Operation Queued"),
            _("%s has been queued.") % description,
            "info",
        )

    def action_export(self):
        self.ensure_one()
        return self._action_queue_method(
            "_export",
            _("Export %(label)s to marketplace: %(name)s")
            % {"label": self._marketplace_product_label(), "name": self.display_name},
        )

    def action_update(self):
        self.ensure_one()
        if self.sync_state != "approved":
            raise UserError(_("Only approved products can be updated."))
        return self._action_queue_method(
            "_update",
            _("Update %(label)s on marketplace: %(name)s")
            % {"label": self._marketplace_product_label(), "name": self.display_name},
        )

    def action_sync_stock_price(self):
        self.ensure_one()
        if self.sync_state != "approved":
            raise UserError(_("Only approved products can have stock/price synced."))
        return self._action_queue_method(
            "_sync_stock_price",
            _("Sync stock/price: %s") % self.display_name,
        )

    def action_set_draft(self):
        self.ensure_one()
        self.write({"sync_state": "draft", "sync_error": False})
        return True
