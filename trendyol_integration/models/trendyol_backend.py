# Copyright 2025 Altinkaya Enclosures
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import logging
from datetime import datetime, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .trendyol_request import TrendyolAPIError, TrendyolRequest

_logger = logging.getLogger(__name__)


class TrendyolBackend(models.Model):
    _name = "trendyol.backend"
    _description = "Trendyol Backend Configuration"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    name = fields.Char(required=True, tracking=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
    )

    # API Credentials
    seller_id = fields.Char(
        string="Seller ID",
        required=True,
        tracking=True,
        help="Your Trendyol seller ID",
    )
    api_key = fields.Char(
        string="API Key",
        required=True,
        groups="trendyol_integration.group_trendyol_manager",
    )
    api_secret = fields.Char(
        string="API Secret",
        required=True,
        groups="trendyol_integration.group_trendyol_manager",
    )
    environment = fields.Selection(
        [
            ("stage", "Stage (Testing)"),
            ("prod", "Production"),
        ],
        default="stage",
        required=True,
        tracking=True,
    )

    # Odoo Mappings
    warehouse_id = fields.Many2one(
        "stock.warehouse",
        string="Warehouse",
        required=True,
        help="Warehouse to use for stock calculations and order fulfillment",
    )
    pricelist_id = fields.Many2one(
        "product.pricelist",
        string="Pricelist",
        required=True,
        help="Pricelist to use for Trendyol prices (must be in TRY)",
    )
    sales_team_id = fields.Many2one(
        "crm.team",
        string="Sales Team",
        help="Default sales team for Trendyol orders",
    )
    fiscal_position_id = fields.Many2one(
        "account.fiscal.position",
        string="Fiscal Position",
        help="Default fiscal position for Trendyol orders",
    )

    # Default Settings
    default_cargo_company_id = fields.Many2one(
        "delivery.carrier",
        string="Default Cargo Company",
        help="Default delivery carrier for Trendyol orders",
    )
    default_product_id = fields.Many2one(
        "product.product",
        string="Default Product",
        help="Fallback product for unmapped Trendyol items. "
        "If not set, unmapped items will be created as note lines.",
    )
    default_vat_rate = fields.Float(
        string="Default VAT Rate (%)",
        default=20.0,
        help="Default VAT rate for products without tax",
    )
    auto_confirm_orders = fields.Boolean(
        string="Auto-confirm Orders",
        default=True,
        help="Automatically confirm imported orders",
    )

    # Sync Settings
    auto_import_orders = fields.Boolean(
        string="Auto Import Orders",
        default=True,
        help="Automatically import orders via scheduled job",
    )
    auto_sync_stock = fields.Boolean(
        string="Auto Sync Stock",
        default=True,
        help="Automatically sync stock levels via scheduled job",
    )
    auto_sync_tracking = fields.Boolean(
        string="Auto Sync Tracking",
        default=True,
        help="Automatically send tracking numbers when delivery is done",
    )
    auto_send_invoice = fields.Boolean(
        string="Auto Send Invoice",
        default=True,
        help="Automatically send invoice link when invoice is posted",
    )
    auto_import_claims = fields.Boolean(
        string="Auto Import Claims",
        default=True,
        help="Automatically import returns/claims via scheduled job",
    )

    # Last Sync Timestamps
    last_order_sync = fields.Datetime(
        string="Last Order Sync",
        readonly=True,
    )
    last_stock_sync = fields.Datetime(
        string="Last Stock Sync",
        readonly=True,
    )
    last_category_sync = fields.Datetime(
        string="Last Category Sync",
        readonly=True,
    )
    last_brand_sync = fields.Datetime(
        string="Last Brand Sync",
        readonly=True,
    )
    last_claim_sync = fields.Datetime(
        string="Last Claim Sync",
        readonly=True,
    )

    # Webhook Configuration
    webhook_url = fields.Char(
        string="Webhook URL",
        readonly=True,
        help="Webhook endpoint URL for this backend",
    )
    webhook_secret = fields.Char(
        string="Webhook Secret",
        groups="trendyol_integration.group_trendyol_manager",
        help="Secret key for webhook authentication",
    )
    webhook_id = fields.Char(
        string="Trendyol Webhook ID",
        readonly=True,
    )

    # Statistics
    product_binding_count = fields.Integer(
        compute="_compute_counts",
        string="Product Bindings",
    )
    order_count = fields.Integer(
        compute="_compute_counts",
        string="Orders",
    )
    claim_count = fields.Integer(
        compute="_compute_counts",
        string="Claims",
    )

    @api.depends()
    def _compute_counts(self):
        ProductBinding = self.env["trendyol.product.binding"]
        Order = self.env["trendyol.order"]
        Claim = self.env["trendyol.claim"]

        for backend in self:
            backend.product_binding_count = ProductBinding.search_count(
                [("backend_id", "=", backend.id)]
            )
            backend.order_count = Order.search_count([("backend_id", "=", backend.id)])
            backend.claim_count = Claim.search_count([("backend_id", "=", backend.id)])

    def _get_api_client(self):
        """Get configured API client for this backend."""
        self.ensure_one()
        return TrendyolRequest(
            seller_id=self.seller_id,
            api_key=self.api_key,
            api_secret=self.api_secret,
            environment=self.environment,
        )

    def action_test_connection(self):
        """Test API connection."""
        self.ensure_one()
        try:
            client = self._get_api_client()
            client.test_connection()
        except TrendyolAPIError as e:
            raise UserError(_("Connection failed: %s") % str(e)) from e

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Success"),
                "message": _("Connection to Trendyol API successful!"),
                "type": "success",
                "sticky": False,
            },
        }

    def action_sync_categories(self):
        """Sync categories from Trendyol."""
        self.ensure_one()
        self.with_delay(
            channel="root.trendyol.product",
            description=_("Sync Trendyol categories: %s") % self.name,
        )._sync_categories()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Sync Started"),
                "message": _("Category synchronization has been queued."),
                "type": "info",
                "sticky": False,
            },
        }

    def _sync_categories(self):
        """Sync categories from Trendyol API."""
        self.ensure_one()
        client = self._get_api_client()
        Category = self.env["trendyol.category"]

        try:
            result = client.get_categories()
            categories = result.get("categories", [])
            Category._sync_from_trendyol(self, categories)
            self.last_category_sync = fields.Datetime.now()
            _logger.info(
                "Synced %d categories for backend %s", len(categories), self.name
            )
        except TrendyolAPIError as e:
            _logger.error("Failed to sync categories: %s", str(e))
            raise

    def action_sync_brands(self):
        """Sync brands from Trendyol."""
        self.ensure_one()
        self.with_delay(
            channel="root.trendyol.product",
            description=_("Sync Trendyol brands: %s") % self.name,
        )._sync_brands()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Sync Started"),
                "message": _("Brand synchronization has been queued."),
                "type": "info",
                "sticky": False,
            },
        }

    def _sync_brands(self):
        """Sync all brands from Trendyol API."""
        self.ensure_one()
        client = self._get_api_client()
        Brand = self.env["trendyol.brand"]

        try:
            page = 0
            total_synced = 0
            while True:
                result = client.get_brands(page=page, size=1000)
                brands = result.get("brands", [])
                if not brands:
                    break

                Brand._sync_from_trendyol(self, brands)
                total_synced += len(brands)
                page += 1

                # Safety limit
                if page > 100:
                    _logger.warning("Brand sync safety limit reached")
                    break

            self.last_brand_sync = fields.Datetime.now()
            _logger.info("Synced %d brands for backend %s", total_synced, self.name)
        except TrendyolAPIError as e:
            _logger.error("Failed to sync brands: %s", str(e))
            raise

    def action_import_orders(self):
        """Manually trigger order import."""
        self.ensure_one()
        self.with_delay(
            channel="root.trendyol.order",
            description=_("Import Trendyol orders: %s") % self.name,
        )._import_orders()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Import Started"),
                "message": _("Order import has been queued."),
                "type": "info",
                "sticky": False,
            },
        }

    def _import_orders(self, status=None):
        """Import orders from Trendyol API.

        Args:
            status: Optional status filter (Created, Picking, Invoiced, Shipped, etc.)
                   If None, fetches all orders regardless of status.
        """
        self.ensure_one()
        client = self._get_api_client()
        Order = self.env["trendyol.order"]

        # Calculate date range
        end_date = datetime.now()
        if self.last_order_sync:
            start_date = self.last_order_sync
        else:
            # First sync: get last 7 days
            start_date = end_date - timedelta(days=7)

        # Convert to milliseconds timestamp
        start_ts = int(start_date.timestamp() * 1000)
        end_ts = int(end_date.timestamp() * 1000)

        try:
            page = 0
            total_imported = 0
            while True:
                result = client.get_orders(
                    status=status,
                    start_date=start_ts,
                    end_date=end_ts,
                    page=page,
                    size=200,
                )
                orders = result.get("content", [])
                if not orders:
                    break

                for order_data in orders:
                    Order._import_order(self, order_data)
                    total_imported += 1

                page += 1
                # Safety limit
                if page > 50:
                    _logger.warning("Order import safety limit reached")
                    break

            self.last_order_sync = fields.Datetime.now()
            _logger.info("Imported %d orders for backend %s", total_imported, self.name)
        except TrendyolAPIError as e:
            _logger.error("Failed to import orders: %s", str(e))
            raise

    def action_sync_stock_prices(self):
        """Manually trigger stock/price sync."""
        self.ensure_one()
        self.with_delay(
            channel="root.trendyol.stock",
            description=_("Sync Trendyol stock/prices: %s") % self.name,
        )._sync_stock_prices()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Sync Started"),
                "message": _("Stock/price synchronization has been queued."),
                "type": "info",
                "sticky": False,
            },
        }

    def _sync_stock_prices(self):
        """Sync stock and prices to Trendyol."""
        self.ensure_one()
        client = self._get_api_client()
        Binding = self.env["trendyol.product.binding"]
        BatchRequest = self.env["trendyol.batch.request"]

        # Get all approved bindings
        bindings = Binding.search(
            [
                ("backend_id", "=", self.id),
                ("sync_state", "=", "approved"),
            ]
        )

        if not bindings:
            _logger.info("No approved bindings to sync for backend %s", self.name)
            return

        items = []
        for binding in bindings:
            item = binding._prepare_stock_price_data()
            if item:
                items.append(item)

        if not items:
            _logger.info("No stock/price changes to sync for backend %s", self.name)
            return

        try:
            # Send in batches of 1000
            for i in range(0, len(items), 1000):
                batch_items = items[i : i + 1000]
                result = client.update_price_and_inventory(batch_items)

                batch_id = result.get("batchRequestId")
                if batch_id:
                    BatchRequest.create(
                        {
                            "backend_id": self.id,
                            "batch_request_id": batch_id,
                            "request_type": "price_inventory",
                            "state": "pending",
                            "total_items": len(batch_items),
                        }
                    )

            self.last_stock_sync = fields.Datetime.now()
            _logger.info(
                "Synced %d stock/price items for backend %s",
                len(items),
                self.name,
            )
        except TrendyolAPIError as e:
            _logger.error("Failed to sync stock/prices: %s", str(e))
            raise

    def action_import_claims(self):
        """Manually trigger claims import."""
        self.ensure_one()
        self.with_delay(
            channel="root.trendyol.order",
            description=_("Import Trendyol claims: %s") % self.name,
        )._import_claims()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Import Started"),
                "message": _("Claims import has been queued."),
                "type": "info",
                "sticky": False,
            },
        }

    def _import_claims(self):
        """Import claims/returns from Trendyol API."""
        self.ensure_one()
        client = self._get_api_client()
        Claim = self.env["trendyol.claim"]

        # Calculate date range
        end_date = datetime.now()
        if self.last_claim_sync:
            start_date = self.last_claim_sync
        else:
            start_date = end_date - timedelta(days=30)

        start_ts = int(start_date.timestamp() * 1000)
        end_ts = int(end_date.timestamp() * 1000)

        try:
            page = 0
            total_imported = 0
            while True:
                result = client.get_claims(
                    start_date=start_ts,
                    end_date=end_ts,
                    page=page,
                    size=25,
                )
                claims = result.get("content", [])
                if not claims:
                    break

                for claim_data in claims:
                    Claim._import_claim(self, claim_data)
                    total_imported += 1

                page += 1
                if page > 100:
                    _logger.warning("Claims import safety limit reached")
                    break

            self.last_claim_sync = fields.Datetime.now()
            _logger.info("Imported %d claims for backend %s", total_imported, self.name)
        except TrendyolAPIError as e:
            _logger.error("Failed to import claims: %s", str(e))
            raise

    def action_check_batch_requests(self):
        """Check status of pending batch requests."""
        self.ensure_one()
        self.with_delay(
            channel="root.trendyol.product",
            description=_("Check Trendyol batch requests: %s") % self.name,
        )._check_batch_requests()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Check Started"),
                "message": _("Batch request check has been queued."),
                "type": "info",
                "sticky": False,
            },
        }

    def _check_batch_requests(self):
        """Check status of pending batch requests."""
        self.ensure_one()
        BatchRequest = self.env["trendyol.batch.request"]

        pending_requests = BatchRequest.search(
            [
                ("backend_id", "=", self.id),
                ("state", "in", ["pending", "processing"]),
            ]
        )

        for request in pending_requests:
            request._check_status()

    def action_view_products(self):
        """View product bindings for this backend."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Product Bindings"),
            "res_model": "trendyol.product.binding",
            "view_mode": "tree,form",
            "domain": [("backend_id", "=", self.id)],
            "context": {"default_backend_id": self.id},
        }

    def action_view_orders(self):
        """View orders for this backend."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Orders"),
            "res_model": "trendyol.order",
            "view_mode": "tree,form",
            "domain": [("backend_id", "=", self.id)],
            "context": {"default_backend_id": self.id},
        }

    def action_view_claims(self):
        """View claims for this backend."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Claims"),
            "res_model": "trendyol.claim",
            "view_mode": "tree,form",
            "domain": [("backend_id", "=", self.id)],
            "context": {"default_backend_id": self.id},
        }

    # ==================== Cron Methods ====================

    @api.model
    def _cron_import_orders(self):
        """Cron job to import orders from all active backends."""
        backends = self.search(
            [
                ("active", "=", True),
                ("auto_import_orders", "=", True),
            ]
        )
        for backend in backends:
            backend.with_delay(
                channel="root.trendyol.order",
                description=_("Import Trendyol orders: %s") % backend.name,
            )._import_orders()

    @api.model
    def _cron_import_claims(self):
        """Cron job to import claims from all active backends."""
        backends = self.search(
            [
                ("active", "=", True),
                ("auto_import_claims", "=", True),
            ]
        )
        for backend in backends:
            backend.with_delay(
                channel="root.trendyol.order",
                description=_("Import Trendyol claims: %s") % backend.name,
            )._import_claims()

    @api.model
    def _cron_sync_stock_prices(self):
        """Cron job to sync stock/prices for all active backends."""
        backends = self.search(
            [
                ("active", "=", True),
                ("auto_sync_stock", "=", True),
            ]
        )
        for backend in backends:
            backend.with_delay(
                channel="root.trendyol.stock",
                description=_("Sync Trendyol stock/prices: %s") % backend.name,
            )._sync_stock_prices()

    @api.model
    def _cron_check_batch_requests(self):
        """Cron job to check batch request status for all active backends."""
        backends = self.search([("active", "=", True)])
        for backend in backends:
            backend.with_delay(
                channel="root.trendyol.product",
                description=_("Check Trendyol batch requests: %s") % backend.name,
            )._check_batch_requests()

    @api.model
    def _cron_sync_metadata(self):
        """Cron job to sync categories and brands for all active backends."""
        backends = self.search([("active", "=", True)])
        for backend in backends:
            backend.with_delay(
                channel="root.trendyol.product",
                description=_("Sync Trendyol metadata: %s") % backend.name,
            )._sync_categories()
            backend.with_delay(
                channel="root.trendyol.product",
                description=_("Sync Trendyol brands: %s") % backend.name,
            )._sync_brands()

    # ==================== Webhook Methods ====================

    def _process_webhook_data(self, data):
        """Process webhook data from Trendyol.

        Args:
            data: Dict from webhook payload
        """
        self.ensure_one()
        Order = self.env["trendyol.order"]

        # Webhook data typically contains order/package updates
        status = data.get("status")
        package_id = str(data.get("shipmentPackageId") or data.get("id") or "")

        if not package_id:
            _logger.warning("Webhook data missing package ID: %s", data)
            return

        # Find existing order
        order = Order.search(
            [
                ("backend_id", "=", self.id),
                ("trendyol_package_id", "=", package_id),
            ],
            limit=1,
        )

        if order:
            # Update status
            new_status = Order._map_status(status)
            if order.trendyol_status != new_status:
                order.trendyol_status = new_status
                _logger.info(
                    "Webhook updated order %s status to %s",
                    order.trendyol_order_number,
                    new_status,
                )

            # Handle cancellation
            if new_status == "cancelled" and order.odoo_id.state not in (
                "done",
                "cancel",
            ):
                order.odoo_id.action_cancel()
                _logger.info("Cancelled Odoo order %s via webhook", order.odoo_id.name)

            # Update tracking info if provided
            tracking = data.get("cargoTrackingNumber")
            if tracking and not order.cargo_tracking_number:
                order.cargo_tracking_number = tracking
                order.cargo_tracking_link = data.get("cargoTrackingLink")

        else:
            # Order not found, try to import it
            _logger.info(
                "Webhook for unknown package %s, attempting import", package_id
            )
            Order._import_order(self, data)
