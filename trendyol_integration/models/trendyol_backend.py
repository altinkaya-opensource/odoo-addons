# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import logging
import secrets
from datetime import UTC, datetime, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .trendyol_request import TrendyolAPIError, TrendyolRequest

_logger = logging.getLogger(__name__)


# Trendyol API uses GMT+3 (Turkey time) for all timestamps
TRENDYOL_UTC_OFFSET = timedelta(hours=3)


def _utc_to_trendyol_ts(dt):
    """Convert a naive UTC datetime to a millisecond timestamp
    for Trendyol API queries.
    """
    return int(dt.replace(tzinfo=UTC).timestamp() * 1000)


def _trendyol_ts_to_utc(ts_ms):
    """Convert a Trendyol timestamp (ms, GMT+3) to naive UTC datetime.

    Returns False if the timestamp is falsy or invalid.
    """
    if not ts_ms:
        return False
    try:
        return (
            datetime.fromtimestamp(ts_ms / 1000, UTC).replace(tzinfo=None)
            - TRENDYOL_UTC_OFFSET
        )
    except (ValueError, TypeError, OSError):
        return False


class TrendyolBackend(models.Model):
    _name = "trendyol.backend"
    _description = "Trendyol Backend Configuration"
    _inherit = ["marketplace.backend.mixin", "mail.thread", "mail.activity.mixin"]

    name = fields.Char(required=True, tracking=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        "res.company",
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
        required=True,
        help="Pricelist to use for Trendyol prices (must be in TRY)",
    )
    sales_team_id = fields.Many2one(
        "crm.team",
        help="Default sales team for Trendyol orders",
    )
    fiscal_position_id = fields.Many2one(
        "account.fiscal.position",
        help="Default fiscal position for Trendyol orders",
    )
    source_id = fields.Many2one(
        "utm.source",
        help="UTM source to set on Trendyol orders",
    )

    # Default Settings
    default_cargo_company_id = fields.Many2one(
        "delivery.carrier",
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

    def _marketplace_name(self):
        return _("Trendyol")

    def _marketplace_queue_channel(self):
        return "root.trendyol.order"

    def _marketplace_api_error_class(self):
        return TrendyolAPIError

    def _marketplace_cargo_provider_field(self):
        return "trendyol_cargo_provider_name"

    def _marketplace_count_models(self):
        return {
            "product_binding_count": "trendyol.product.binding",
            "order_count": "trendyol.order",
            "claim_count": "trendyol.claim",
            "question_count": "trendyol.question",
            "settlement_count": "trendyol.settlement",
        }

    def _get_api_client(self):
        """Get configured API client for this backend."""
        self.ensure_one()
        return TrendyolRequest(
            seller_id=self.seller_id,
            api_key=self.api_key,
            api_secret=self.api_secret,
            environment=self.environment,
        )

    def action_register_webhook(self):
        """Register a webhook subscription on Trendyol."""
        self.ensure_one()
        if self.webhook_id:
            raise UserError(_("A webhook is already registered for this backend."))

        base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url")
        webhook_url = f"{base_url}/ty/wh/{self.id}"

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
                total_pages = result.get("totalPages")
                if total_pages is not None and page + 1 >= total_pages:
                    break
                page += 1

                if page >= 1000:
                    raise UserError(_("Brand synchronization page limit reached."))

            self.last_brand_sync = fields.Datetime.now()
            _logger.info("Synced %d brands for backend %s", total_synced, self.name)
        except TrendyolAPIError as e:
            _logger.error("Failed to sync brands: %s", str(e))
            raise

    def action_import_orders(self):
        """Manually trigger order import."""
        self.ensure_one()
        return self._marketplace_queue_action(
            "_import_orders",
            _("Import Trendyol orders: %s") % self.name,
            _("Import Started"),
            _("Order import has been queued."),
        )

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
        end_date = fields.Datetime.now()
        if self.last_order_sync:
            start_date = self.last_order_sync
        else:
            # First sync: get last 7 days
            start_date = end_date - timedelta(days=7)

        # Convert to milliseconds timestamp
        start_ts = _utc_to_trendyol_ts(start_date)
        end_ts = _utc_to_trendyol_ts(end_date)

        try:
            page = 0
            total_imported = 0
            failed_packages = []
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
                    package_id = order_data.get(
                        "shipmentPackageId", order_data.get("id")
                    )
                    try:
                        with self.env.cr.savepoint():
                            if Order._import_order(self, order_data):
                                total_imported += 1
                    except Exception:
                        failed_packages.append(str(package_id or "unknown"))
                        _logger.exception(
                            "Failed to import order package %s", package_id
                        )

                total_pages = result.get("totalPages")
                if total_pages is not None and page + 1 >= total_pages:
                    break
                page += 1
                if page >= 1000:
                    raise UserError(_("Order import page limit reached."))

            if not failed_packages:
                self.last_order_sync = end_date
            else:
                _logger.error(
                    "%d Trendyol package(s) failed; keeping the previous order "
                    "sync cursor so they are retried",
                    len(failed_packages),
                )
            _logger.info("Imported %d orders for backend %s", total_imported, self.name)
        except TrendyolAPIError as e:
            _logger.error("Failed to import orders: %s", str(e))
            raise

    def action_sync_stock_prices(self):
        """Manually trigger stock/price sync."""
        self.ensure_one()
        return self._marketplace_queue_action(
            "_sync_stock_prices",
            _("Sync Trendyol stock/prices: %s") % self.name,
            _("Sync Started"),
            _("Stock/price synchronization has been queued."),
            channel="root.trendyol.stock",
        )

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

        binding_items = []
        for binding in bindings:
            item = binding._prepare_stock_price_data()
            if item:
                binding_items.append((binding, item))

        if not binding_items:
            _logger.info("No stock/price changes to sync for backend %s", self.name)
            return

        try:
            # Send in batches of 1000
            for i in range(0, len(binding_items), 1000):
                batch_pairs = binding_items[i : i + 1000]
                batch_items = [item for _binding, item in batch_pairs]
                batch_bindings = Binding.browse(
                    [binding.id for binding, _item in batch_pairs]
                )
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
                            "product_binding_ids": [(6, 0, batch_bindings.ids)],
                        }
                    )

            self.last_stock_sync = fields.Datetime.now()
            _logger.info(
                "Synced %d stock/price items for backend %s",
                len(binding_items),
                self.name,
            )
        except TrendyolAPIError as e:
            _logger.error("Failed to sync stock/prices: %s", str(e))
            raise

    def action_import_claims(self):
        """Manually trigger claims import."""
        self.ensure_one()
        return self._marketplace_queue_action(
            "_import_claims",
            _("Import Trendyol claims: %s") % self.name,
            _("Import Started"),
            _("Claims import has been queued."),
        )

    def _import_claims(self):
        """Import claims/returns from Trendyol API."""
        self.ensure_one()
        client = self._get_api_client()
        Claim = self.env["trendyol.claim"]

        # Calculate date range
        end_date = fields.Datetime.now()
        if self.last_claim_sync:
            start_date = self.last_claim_sync
        else:
            start_date = end_date - timedelta(days=30)

        start_ts = _utc_to_trendyol_ts(start_date)
        end_ts = _utc_to_trendyol_ts(end_date)

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

                total_pages = result.get("totalPages")
                if total_pages is not None and page + 1 >= total_pages:
                    break
                page += 1
                if page >= 1000:
                    raise UserError(_("Claims import page limit reached."))

            # Date filters operate on claimDate, so changed older claims are not
            # returned by the incremental window. Refresh every non-terminal
            # claim explicitly by ID to keep line-level statuses current.
            active_claims = Claim.search(
                [
                    ("backend_id", "=", self.id),
                    (
                        "claim_status",
                        "in",
                        [
                            "created",
                            "waiting_in_action",
                            "waiting_fraud_check",
                            "in_analysis",
                            "unresolved",
                        ],
                    ),
                ]
            )
            failed_refreshes = []
            for offset in range(0, len(active_claims), 25):
                chunk = active_claims[offset : offset + 25]
                try:
                    with self.env.cr.savepoint():
                        result = client.get_claims(
                            claim_ids=chunk.mapped("trendyol_claim_id"),
                            page=0,
                            size=25,
                        )
                        for claim_data in result.get("content", []):
                            Claim._import_claim(self, claim_data)
                except Exception as error:
                    failed_refreshes.append(str(error))
                    _logger.exception(
                        "Failed to refresh Trendyol claims %s",
                        chunk.mapped("trendyol_claim_id"),
                    )

            if failed_refreshes:
                _logger.error(
                    "%d Trendyol claim refresh chunk(s) failed: %s",
                    len(failed_refreshes),
                    "; ".join(failed_refreshes),
                )

            self.last_claim_sync = end_date
            _logger.info("Imported %d claims for backend %s", total_imported, self.name)
        except TrendyolAPIError as e:
            _logger.error("Failed to import claims: %s", str(e))
            raise

    def action_check_batch_requests(self):
        """Check status of pending batch requests."""
        self.ensure_one()
        return self._marketplace_queue_action(
            "_check_batch_requests",
            _("Check Trendyol batch requests: %s") % self.name,
            _("Check Started"),
            _("Batch request check has been queued."),
            channel="root.trendyol.product",
        )

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
        return self._marketplace_action_view(
            _("Product Bindings"), "trendyol.product.binding"
        )

    def action_view_orders(self):
        """View orders for this backend."""
        return self._marketplace_action_view(_("Orders"), "trendyol.order")

    def action_view_claims(self):
        """View claims for this backend."""
        return self._marketplace_action_view(_("Claims"), "trendyol.claim")

    def action_import_questions(self):
        """Manually trigger question import."""
        self.ensure_one()
        return self._marketplace_queue_action(
            "_import_questions",
            _("Import Trendyol questions: %s") % self.name,
            _("Import Started"),
            _("Question import has been queued."),
        )

    def _import_questions(self):
        """Import customer questions from Trendyol API."""
        self.ensure_one()
        client = self._get_api_client()
        Question = self.env["trendyol.question"]

        # Calculate date range (API max 2 weeks)
        end_date = fields.Datetime.now()
        if self.last_question_sync:
            start_date = self.last_question_sync
        else:
            start_date = end_date - timedelta(days=14)

        try:
            total_imported = 0
            window_start = start_date
            while window_start < end_date:
                window_end = min(window_start + timedelta(days=14), end_date)
                page = 0
                while True:
                    result = client.get_questions(
                        status="WAITING_FOR_ANSWER",
                        start_date=_utc_to_trendyol_ts(window_start),
                        end_date=_utc_to_trendyol_ts(window_end),
                        page=page,
                        size=50,
                    )
                    questions = result.get("content", [])
                    if not questions:
                        break

                    for question_data in questions:
                        question, is_new = Question._import_question(
                            self, question_data
                        )
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

                    total_pages = result.get("totalPages")
                    if total_pages is not None and page + 1 >= total_pages:
                        break
                    page += 1
                    if page >= 1000:
                        raise UserError(_("Question import page limit reached."))
                window_start = window_end

            # Questions change status after their creation window. Refresh all
            # active records by ID so answers, approvals, and rejections settle.
            active_questions = Question.search(
                [
                    ("backend_id", "=", self.id),
                    (
                        "status",
                        "in",
                        ["waiting_for_answer", "waiting_for_approve"],
                    ),
                ]
            )
            for question in active_questions:
                try:
                    question_data = client.get_question(
                        int(question.trendyol_question_id)
                    )
                except TrendyolAPIError as error:
                    if error.status_code == 404:
                        question.status = "unanswered"
                        continue
                    raise
                Question._import_question(self, question_data)

            self.last_question_sync = end_date
            _logger.info(
                "Imported %d questions for backend %s", total_imported, self.name
            )
        except TrendyolAPIError as e:
            _logger.error("Failed to import questions: %s", str(e))
            raise

    def action_view_questions(self):
        """View questions for this backend."""
        return self._marketplace_action_view(_("Questions"), "trendyol.question")

    # ==================== Settlement Methods ====================

    def action_import_settlements(self):
        """Manually trigger settlement import."""
        self.ensure_one()
        return self._marketplace_queue_action(
            "_import_settlements",
            _("Import Trendyol settlements: %s") % self.name,
            _("Import Started"),
            _("Settlement import has been queued."),
        )

    def _import_settlements(self):
        """Import settlements from Trendyol finance API.

        The API has a max 15-day date range. We iterate in 15-day windows
        from last_settlement_sync (or 15 days ago) to now.
        """
        self.ensure_one()
        client = self._get_api_client()
        Settlement = self.env["trendyol.settlement"]

        end_date = fields.Datetime.now()
        if self.last_settlement_sync:
            start_date = self.last_settlement_sync
        else:
            start_date = end_date - timedelta(days=15)

        # Iterate in 15-day windows
        window_start = start_date
        total_imported = 0

        while window_start < end_date:
            window_end = min(window_start + timedelta(days=15), end_date)
            start_ts = _utc_to_trendyol_ts(window_start)
            end_ts = _utc_to_trendyol_ts(window_end)

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
                        Settlement._import_settlement(self, item)
                        total_imported += 1

                    total_pages = result.get("totalPages")
                    if total_pages is not None and page + 1 >= total_pages:
                        break
                    page += 1
                    if page >= 1000:
                        raise UserError(_("Settlement import page limit reached."))

            except TrendyolAPIError as e:
                _logger.error(
                    "Failed to import settlements for window %s - %s: %s",
                    window_start,
                    window_end,
                    str(e),
                )
                raise

            window_start = window_end

        if self.auto_reconcile_settlements:
            settlements = Settlement.search(
                [
                    ("backend_id", "=", self.id),
                    ("state", "in", ["imported", "error"]),
                    ("manual_review_required", "=", False),
                ]
            )
            for settlement in settlements:
                if (
                    settlement.state == "reconciled"
                    or settlement.manual_review_required
                ):
                    continue
                try:
                    with self.env.cr.savepoint():
                        settlement._reconcile()
                except Exception as error:
                    vals = {"state": "error"}
                    if settlement.error_message != str(error):
                        vals["error_message"] = str(error)
                    settlement.write(vals)
                    _logger.warning(
                        "Auto-reconcile failed for settlement %s: %s",
                        settlement.trendyol_settlement_id,
                        str(error),
                    )

        self.last_settlement_sync = end_date
        _logger.info(
            "Imported %d settlements for backend %s", total_imported, self.name
        )

    def action_view_settlements(self):
        """View settlements for this backend."""
        return self._marketplace_action_view(_("Settlements"), "trendyol.settlement")

    # ==================== Cron Methods ====================

    @api.model
    def _cron_import_orders(self):
        """Cron job to import orders from all active backends."""
        self._marketplace_cron_queue(
            "auto_import_orders",
            "_import_orders",
            _("Import Trendyol orders: %s"),
        )

    @api.model
    def _cron_import_claims(self):
        """Cron job to import claims from all active backends."""
        self._marketplace_cron_queue(
            "auto_import_claims",
            "_import_claims",
            _("Import Trendyol claims: %s"),
        )

    @api.model
    def _cron_import_questions(self):
        """Cron job to import customer questions from all active backends."""
        self._marketplace_cron_queue(
            "auto_import_questions",
            "_import_questions",
            _("Import Trendyol questions: %s"),
        )

    @api.model
    def _cron_import_settlements(self):
        """Cron job to import settlements from all active backends."""
        self._marketplace_cron_queue(
            "auto_import_settlements",
            "_import_settlements",
            _("Import Trendyol settlements: %s"),
        )

    @api.model
    def _cron_sync_stock_prices(self):
        """Cron job to sync stock/prices for all active backends."""
        self._marketplace_cron_queue(
            "auto_sync_stock",
            "_sync_stock_prices",
            _("Sync Trendyol stock/prices: %s"),
            channel="root.trendyol.stock",
        )

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
        return self._send_pending_marketplace_invoices(
            "trendyol.order",
            "trendyol_order_number",
        )

    # ==================== Webhook Methods ====================

    def _process_webhook_data(self, data):
        """Process webhook data from Trendyol.

        Args:
            data: Dict from webhook payload
        """
        self.ensure_one()
        Order = self.env["trendyol.order"]

        packages = data.get("content") if isinstance(data, dict) else None
        if packages is None:
            packages = [data]
        if not isinstance(packages, list):
            raise ValueError("Invalid Trendyol webhook content")

        for package_data in packages:
            if not isinstance(package_data, dict):
                _logger.warning("Ignoring invalid Trendyol webhook package")
                continue
            package_value = package_data.get("shipmentPackageId") or package_data.get(
                "id"
            )
            if not package_value:
                _logger.warning("Trendyol webhook package is missing its ID")
                continue
            package_id = str(package_value)
            order = Order.search(
                [
                    ("backend_id", "=", self.id),
                    ("trendyol_package_id", "=", package_id),
                ],
                limit=1,
            )
            if order:
                order._update_from_trendyol_data(package_data)
            else:
                _logger.info("Webhook for unknown package %s, importing it", package_id)
                Order._import_order(self, package_data)
