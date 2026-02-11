# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import logging
import secrets
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
    warehouse_ids = fields.Many2many(
        "stock.warehouse",
        string="Warehouses",
        required=True,
        help="Warehouses to use for stock calculations and order fulfillment",
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
    cargo_mapping_ids = fields.One2many(
        "trendyol.cargo.mapping",
        "backend_id",
        string="Cargo Mappings",
        help="Map Trendyol cargo providers to Odoo delivery carriers",
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
        default=True,
        help="Automatically import orders via scheduled job",
    )
    auto_sync_stock = fields.Boolean(
        default=True,
        help="Automatically sync stock levels via scheduled job",
    )
    auto_sync_tracking = fields.Boolean(
        default=True,
        help="Automatically send tracking numbers when delivery is done",
    )
    auto_send_invoice = fields.Boolean(
        default=True,
        help="Send invoice links to Trendyol via nightly batch cron",
    )
    auto_import_claims = fields.Boolean(
        default=True,
        help="Automatically import returns/claims via scheduled job",
    )
    auto_import_questions = fields.Boolean(
        default=True,
        help="Automatically import customer questions via scheduled job",
    )

    # Last Sync Timestamps
    last_order_sync = fields.Datetime(
        readonly=True,
    )
    last_stock_sync = fields.Datetime(
        readonly=True,
    )
    last_category_sync = fields.Datetime(
        readonly=True,
    )
    last_brand_sync = fields.Datetime(
        readonly=True,
    )
    last_claim_sync = fields.Datetime(
        readonly=True,
    )
    last_question_sync = fields.Datetime(
        readonly=True,
    )

    # Settlement / Accounting Settings
    trendyol_partner_id = fields.Many2one(
        "res.partner",
        string="Trendyol Partner",
        help="Partner record representing Trendyol. Used as reference on "
        "settlement payments and for reporting purposes.",
    )
    settlement_journal_id = fields.Many2one(
        "account.journal",
        string="Trendyol Payment Journal",
        domain="[('type', '=', 'bank')]",
        help="Intermediary bank-type journal for Trendyol payments. "
        "When a real bank transfer arrives, reconcile against this journal.",
    )
    auto_import_settlements = fields.Boolean(
        default=True,
        help="Automatically import financial settlements via scheduled job",
    )
    auto_reconcile_settlements = fields.Boolean(
        default=True,
        help="Automatically reconcile imported settlements with invoices",
    )
    last_settlement_sync = fields.Datetime(
        readonly=True,
    )

    # Printing
    label_printer_id = fields.Many2one(
        "printing.printer",
        string="Label Printer",
        help="Default ZPL label printer for Trendyol shipping labels. "
        "Used when the delivery carrier has no printer configured.",
    )

    # Q&A Settings
    question_user_ids = fields.Many2many(
        "res.users",
        "trendyol_backend_question_user_rel",
        "backend_id",
        "user_id",
        string="Q&A Notification Users",
        help="Users to notify when new customer questions are imported",
    )

    # Webhook Configuration
    webhook_url = fields.Char(
        string="Webhook URL",
        readonly=True,
        help="Webhook endpoint URL for this backend",
    )
    webhook_api_key = fields.Char(
        string="Webhook API Key",
        groups="trendyol_integration.group_trendyol_manager",
        help="API key that Trendyol sends in x-api-key header "
        "when calling the webhook endpoint.",
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
    question_count = fields.Integer(
        compute="_compute_counts",
        string="Questions",
    )
    settlement_count = fields.Integer(
        compute="_compute_counts",
        string="Settlements",
    )

    @api.depends()
    def _compute_counts(self):
        ProductBinding = self.env["trendyol.product.binding"]
        Order = self.env["trendyol.order"]
        Claim = self.env["trendyol.claim"]
        Question = self.env["trendyol.question"]
        Settlement = self.env["trendyol.settlement"]

        for backend in self:
            backend.product_binding_count = ProductBinding.search_count(
                [("backend_id", "=", backend.id)]
            )
            backend.order_count = Order.search_count([("backend_id", "=", backend.id)])
            backend.claim_count = Claim.search_count([("backend_id", "=", backend.id)])
            backend.question_count = Question.search_count(
                [("backend_id", "=", backend.id)]
            )
            backend.settlement_count = Settlement.search_count(
                [("backend_id", "=", backend.id)]
            )

    def _get_api_client(self):
        """Get configured API client for this backend."""
        self.ensure_one()
        return TrendyolRequest(
            seller_id=self.seller_id,
            api_key=self.api_key,
            api_secret=self.api_secret,
            environment=self.environment,
        )

    def _get_carrier_for_cargo_provider(self, cargo_provider_name):
        """Get delivery carrier for a Trendyol cargo provider name.

        Searches cargo_mapping_ids by trendyol_cargo_provider_name (exact match,
        case-insensitive). Falls back to default_cargo_company_id if no mapping
        is found.

        Args:
            cargo_provider_name: Cargo provider name from Trendyol API

        Returns:
            delivery.carrier record or False
        """
        self.ensure_one()
        if cargo_provider_name:
            name_lower = cargo_provider_name.lower()
            mapping = self.cargo_mapping_ids.filtered(
                lambda m: m.trendyol_cargo_provider_name
                and m.trendyol_cargo_provider_name.lower() == name_lower
            )
            if mapping:
                return mapping[0].carrier_id
        return self.default_cargo_company_id

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

    def action_register_webhook(self):
        """Register a webhook subscription on Trendyol."""
        self.ensure_one()
        if self.webhook_id:
            raise UserError(_("A webhook is already registered for this backend."))

        base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url")
        webhook_url = f"{base_url}/trendyol/webhook/{self.id}"

        # Generate API key if not set
        if not self.webhook_api_key:
            self.webhook_api_key = secrets.token_urlsafe(32)

        try:
            client = self._get_api_client()
            result = client.create_webhook(
                webhook_url,
                api_key=self.webhook_api_key,
                authentication_type="API_KEY",
            )
        except TrendyolAPIError as e:
            raise UserError(_("Failed to register webhook: %s") % str(e)) from e

        self.webhook_id = str(result.get("id", ""))
        self.webhook_url = webhook_url

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Webhook Registered"),
                "message": _("Webhook has been registered on Trendyol."),
                "type": "success",
                "sticky": False,
            },
        }

    def action_delete_webhook(self):
        """Delete the webhook subscription from Trendyol."""
        self.ensure_one()
        if not self.webhook_id:
            raise UserError(_("No webhook is registered for this backend."))

        try:
            client = self._get_api_client()
            client.delete_webhook(self.webhook_id)
        except TrendyolAPIError as e:
            raise UserError(_("Failed to delete webhook: %s") % str(e)) from e

        self.webhook_id = False
        self.webhook_url = False

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Webhook Deleted"),
                "message": _("Webhook has been deleted from Trendyol."),
                "type": "success",
                "sticky": False,
            },
        }

    def action_activate_webhook(self):
        """Activate a deactivated webhook on Trendyol."""
        self.ensure_one()
        if not self.webhook_id:
            raise UserError(_("No webhook is registered for this backend."))

        try:
            client = self._get_api_client()
            client.activate_webhook(self.webhook_id)
        except TrendyolAPIError as e:
            raise UserError(_("Failed to activate webhook: %s") % str(e)) from e

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Webhook Activated"),
                "message": _("Webhook has been activated on Trendyol."),
                "type": "success",
                "sticky": False,
            },
        }

    def action_deactivate_webhook(self):
        """Deactivate an active webhook on Trendyol."""
        self.ensure_one()
        if not self.webhook_id:
            raise UserError(_("No webhook is registered for this backend."))

        try:
            client = self._get_api_client()
            client.deactivate_webhook(self.webhook_id)
        except TrendyolAPIError as e:
            raise UserError(_("Failed to deactivate webhook: %s") % str(e)) from e

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Webhook Deactivated"),
                "message": _("Webhook has been deactivated on Trendyol."),
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

    def action_import_questions(self):
        """Manually trigger question import."""
        self.ensure_one()
        self.with_delay(
            channel="root.trendyol.order",
            description=_("Import Trendyol questions: %s") % self.name,
        )._import_questions()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Import Started"),
                "message": _("Question import has been queued."),
                "type": "info",
                "sticky": False,
            },
        }

    def _import_questions(self):
        """Import customer questions from Trendyol API."""
        self.ensure_one()
        client = self._get_api_client()
        Question = self.env["trendyol.question"]

        # Calculate date range (API max 2 weeks)
        end_date = datetime.now()
        if self.last_question_sync:
            start_date = self.last_question_sync
        else:
            start_date = end_date - timedelta(days=14)

        start_ts = int(start_date.timestamp() * 1000)
        end_ts = int(end_date.timestamp() * 1000)

        try:
            page = 0
            total_imported = 0
            while True:
                result = client.get_questions(
                    status="WAITING_FOR_ANSWER",
                    start_date=start_ts,
                    end_date=end_ts,
                    page=page,
                    size=100,
                )
                questions = result.get("content", [])
                if not questions:
                    break

                for question_data in questions:
                    question, is_new = Question._import_question(self, question_data)
                    if question and is_new and self.question_user_ids:
                        activity_type = self.env.ref("mail.mail_activity_data_todo")
                        for user in self.question_user_ids:
                            self.env["mail.activity"].sudo().create(
                                {
                                    "res_model_id": self.env["ir.model"]
                                    .sudo()
                                    ._get("trendyol.question")
                                    .id,
                                    "res_id": question.id,
                                    "activity_type_id": activity_type.id,
                                    "user_id": user.id,
                                    "summary": _(
                                        "New question from %(customer)s",
                                        customer=question.customer_name,
                                    ),
                                    "note": question.question_text,
                                }
                            )
                    total_imported += 1

                page += 1
                if page > 50:
                    _logger.warning("Question import safety limit reached")
                    break

            self.last_question_sync = fields.Datetime.now()
            _logger.info(
                "Imported %d questions for backend %s", total_imported, self.name
            )
        except TrendyolAPIError as e:
            _logger.error("Failed to import questions: %s", str(e))
            raise

    def action_view_questions(self):
        """View questions for this backend."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Questions"),
            "res_model": "trendyol.question",
            "view_mode": "tree,form",
            "domain": [("backend_id", "=", self.id)],
            "context": {"default_backend_id": self.id},
        }

    # ==================== Settlement Methods ====================

    def action_import_settlements(self):
        """Manually trigger settlement import."""
        self.ensure_one()
        self.with_delay(
            channel="root.trendyol.order",
            description=_("Import Trendyol settlements: %s") % self.name,
        )._import_settlements()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Import Started"),
                "message": _("Settlement import has been queued."),
                "type": "info",
                "sticky": False,
            },
        }

    def _import_settlements(self):
        """Import settlements from Trendyol finance API.

        The API has a max 15-day date range. We iterate in 15-day windows
        from last_settlement_sync (or 15 days ago) to now.
        """
        self.ensure_one()
        client = self._get_api_client()
        Settlement = self.env["trendyol.settlement"]

        end_date = datetime.now()
        if self.last_settlement_sync:
            start_date = self.last_settlement_sync
        else:
            start_date = end_date - timedelta(days=15)

        # Iterate in 15-day windows
        window_start = start_date
        total_imported = 0

        while window_start < end_date:
            window_end = min(window_start + timedelta(days=15), end_date)
            start_ts = int(window_start.timestamp() * 1000)
            end_ts = int(window_end.timestamp() * 1000)

            try:
                page = 0
                while True:
                    result = client.get_settlements(
                        start_date=start_ts,
                        end_date=end_ts,
                        transaction_types="Sale,Return",
                        page=page,
                        size=500,
                    )
                    content = result.get("content", [])
                    if not content:
                        break

                    for item in content:
                        settlement = Settlement._import_settlement(self, item)
                        if (
                            settlement
                            and settlement.state == "imported"
                            and self.auto_reconcile_settlements
                        ):
                            try:
                                settlement._reconcile()
                            except Exception as e:
                                settlement.write(
                                    {
                                        "state": "error",
                                        "error_message": str(e),
                                    }
                                )
                                _logger.warning(
                                    "Auto-reconcile failed for settlement %s: %s",
                                    settlement.trendyol_settlement_id,
                                    str(e),
                                )
                        total_imported += 1

                    page += 1
                    if page > 50:
                        _logger.warning("Settlement import safety limit reached")
                        break

            except TrendyolAPIError as e:
                _logger.error(
                    "Failed to import settlements for window %s - %s: %s",
                    window_start,
                    window_end,
                    str(e),
                )
                raise

            window_start = window_end

        self.last_settlement_sync = fields.Datetime.now()
        _logger.info(
            "Imported %d settlements for backend %s", total_imported, self.name
        )

    def action_view_settlements(self):
        """View settlements for this backend."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Settlements"),
            "res_model": "trendyol.settlement",
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
    def _cron_import_questions(self):
        """Cron job to import customer questions from all active backends."""
        backends = self.search(
            [
                ("active", "=", True),
                ("auto_import_questions", "=", True),
            ]
        )
        for backend in backends:
            backend.with_delay(
                channel="root.trendyol.order",
                description=_("Import Trendyol questions: %s") % backend.name,
            )._import_questions()

    @api.model
    def _cron_import_settlements(self):
        """Cron job to import settlements from all active backends."""
        backends = self.search(
            [
                ("active", "=", True),
                ("auto_import_settlements", "=", True),
            ]
        )
        for backend in backends:
            backend.with_delay(
                channel="root.trendyol.order",
                description=_("Import Trendyol settlements: %s") % backend.name,
            )._import_settlements()

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

    @api.model
    def _cron_send_invoices(self):
        """Cron job to send invoice links for all active backends."""
        backends = self.search(
            [
                ("active", "=", True),
                ("auto_send_invoice", "=", True),
            ]
        )
        for backend in backends:
            backend._send_pending_invoices()

    def _send_pending_invoices(self):
        """Find Trendyol orders with pending invoices and queue sends."""
        self.ensure_one()
        orders = self.env["trendyol.order"].search(
            [
                ("backend_id", "=", self.id),
                ("invoice_link_sent", "=", False),
            ]
        )
        for order in orders:
            posted_invoice = order.odoo_id.invoice_ids.filtered(
                lambda i: i.state == "posted" and i.move_type == "out_invoice"
            )
            if not posted_invoice:
                continue
            order.with_delay(
                channel="root.trendyol.order",
                description=_("Send invoice: %s") % order.trendyol_order_number,
            )._send_invoice()

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
                order.odoo_id.with_context(
                    from_trendyol_cancel=True,
                    disable_cancel_warning=True,
                ).action_cancel()
                _logger.info("Cancelled Odoo order %s via webhook", order.odoo_id.name)

            # Update picking delivery state
            order._update_picking_delivery_state(new_status)

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
