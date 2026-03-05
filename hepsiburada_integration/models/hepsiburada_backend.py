# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import logging
from datetime import datetime, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .hepsiburada_request import HepsiburadaAPIError, HepsiburadaRequest

_logger = logging.getLogger(__name__)


class HepsiburadaBackend(models.Model):
    _name = "hepsiburada.backend"
    _description = "Hepsiburada Backend Configuration"
    _inherit = ["marketplace.backend", "mail.thread", "mail.activity.mixin"]

    # API Credentials (Hepsiburada-specific)
    merchant_id = fields.Char(
        string="Merchant ID",
        required=True,
        tracking=True,
        help="GUID merchant identifier from Hepsiburada",
    )
    hb_username = fields.Char(
        string="API Username",
        required=True,
        groups="hepsiburada_integration.group_hepsiburada_manager",
    )
    hb_password = fields.Char(
        string="API Password",
        required=True,
        groups="hepsiburada_integration.group_hepsiburada_manager",
    )
    hb_user_agent = fields.Char(
        string="Developer Username",
        groups="hepsiburada_integration.group_hepsiburada_manager",
        help="Developer username sent as User-Agent header (required by HB API)",
    )

    # Hepsiburada-specific mappings
    cargo_mapping_ids = fields.One2many(
        "hepsiburada.cargo.mapping",
        "backend_id",
        string="Cargo Mappings",
        help="Map Hepsiburada cargo providers to Odoo delivery carriers",
    )

    # Hepsiburada-specific sync settings
    auto_import_questions = fields.Boolean(
        default=True,
        help="Automatically import customer questions via scheduled job",
    )
    dispatch_days = fields.Integer(
        string="Dispatch Time (days)",
        default=3,
        help="Number of days until shipment for listing inventory updates",
    )

    # Manual order import parameters
    import_orders_limit = fields.Integer(
        string="Limit",
        default=5,
        help="Number of packages to fetch per manual import (1–10)",
    )
    import_orders_offset = fields.Integer(
        string="Offset",
        default=0,
        help="Pagination offset for manual order import",
    )

    # Hepsiburada-specific sync timestamps
    last_category_sync = fields.Datetime(readonly=True)
    last_brand_sync = fields.Datetime(readonly=True)
    last_question_sync = fields.Datetime(readonly=True)
    last_settlement_sync = fields.Datetime(readonly=True)
    last_product_import_sync = fields.Datetime(readonly=True)

    # Q&A Settings
    question_user_ids = fields.Many2many(
        "res.users",
        "hepsiburada_backend_question_user_rel",
        "backend_id",
        "user_id",
        string="Q&A Notification Users",
        help="Users to notify when new customer questions are imported",
    )

    # Statistics
    order_count = fields.Integer(
        compute="_compute_counts",
        string="Orders",
    )
    question_count = fields.Integer(
        compute="_compute_counts",
        string="Questions",
    )
    claim_count = fields.Integer(
        compute="_compute_counts",
        string="Claims",
    )
    settlement_count = fields.Integer(
        compute="_compute_counts",
        string="Settlements",
    )
    product_count = fields.Integer(
        compute="_compute_counts",
        string="Products",
    )

    @api.depends()
    def _compute_counts(self):
        Order = self.env["hepsiburada.order"]
        Question = self.env["hepsiburada.question"]
        Claim = self.env["hepsiburada.claim"]
        Settlement = self.env["hepsiburada.settlement"]
        Product = self.env["hepsiburada.product.binding"]
        for backend in self:
            domain = [("backend_id", "=", backend.id)]
            backend.order_count = Order.search_count(domain)
            backend.question_count = Question.search_count(domain)
            backend.claim_count = Claim.search_count(domain)
            backend.settlement_count = Settlement.search_count(domain)
            backend.product_count = Product.search_count(domain)

    def _get_api_client(self):
        """Get configured API client for this backend."""
        self.ensure_one()
        return HepsiburadaRequest(
            merchant_id=self.merchant_id,
            username=self.hb_username,
            password=self.hb_password,
            user_agent=self.hb_user_agent,
            environment=self.environment,
        )

    # ==================== Action Buttons ====================

    def action_test_connection(self):
        """Test API connection by calling get_cargo_firms."""
        self.ensure_one()
        try:
            client = self._get_api_client()
            client.test_connection()
        except HepsiburadaAPIError as e:
            raise UserError(_("Connection failed: %s") % str(e)) from e

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Success"),
                "message": _("Connection to Hepsiburada API successful!"),
                "type": "success",
                "sticky": False,
            },
        }

    def action_import_orders(self):
        """Manually trigger order import from the orders endpoint."""
        self.ensure_one()
        self.with_delay(
            channel="root.hepsiburada.order",
            description=_("Import Hepsiburada orders: %s") % self.name,
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

    def action_import_products(self):
        """Manually trigger product import from Hepsiburada listings."""
        self.ensure_one()
        self.with_delay(
            channel="root.hepsiburada.product",
            description=_("Import Hepsiburada products: %s") % self.name,
        )._import_products()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Import Started"),
                "message": _("Product import has been queued."),
                "type": "info",
                "sticky": False,
            },
        }

    def action_view_orders(self):
        """View orders for this backend."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Orders"),
            "res_model": "hepsiburada.order",
            "view_mode": "tree,form",
            "domain": [("backend_id", "=", self.id)],
            "context": {"default_backend_id": self.id},
        }

    def action_view_questions(self):
        """View questions for this backend."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Questions"),
            "res_model": "hepsiburada.question",
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
            "res_model": "hepsiburada.claim",
            "view_mode": "tree,form",
            "domain": [("backend_id", "=", self.id)],
            "context": {"default_backend_id": self.id},
        }

    def action_view_settlements(self):
        """View settlements for this backend."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Settlements"),
            "res_model": "hepsiburada.settlement",
            "view_mode": "tree,form",
            "domain": [("backend_id", "=", self.id)],
            "context": {"default_backend_id": self.id},
        }

    def action_view_products(self):
        """View product bindings for this backend."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Products"),
            "res_model": "hepsiburada.product.binding",
            "view_mode": "tree,form",
            "domain": [("backend_id", "=", self.id)],
            "context": {"default_backend_id": self.id},
        }

    # ==================== Sync Actions ====================

    def action_sync_categories(self):
        """Sync categories from Hepsiburada."""
        self.ensure_one()
        self.with_delay(
            channel="root.hepsiburada.product",
            description=_("Sync Hepsiburada categories: %s") % self.name,
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
        """Sync categories from Hepsiburada API (paginated flat list)."""
        self.ensure_one()
        client = self._get_api_client()
        Category = self.env["hepsiburada.category"]

        try:
            all_categories = []
            page = 0

            while True:
                result = client.get_categories(
                    leaf=True, status="ACTIVE", available=True, page=page, size=1000
                )
                items = result.get("data") or []
                if not items:
                    break

                all_categories.extend(items)
                if result.get("last", True):
                    break
                page += 1

            if all_categories:
                Category._sync_from_hepsiburada(self, all_categories)

            self.last_category_sync = fields.Datetime.now()
            _logger.info(
                "Synced %d categories for HB backend %s",
                len(all_categories),
                self.name,
            )
        except HepsiburadaAPIError as e:
            _logger.error("Failed to sync HB categories: %s", str(e))
            raise

    def action_sync_brands(self):
        """Sync brands from Hepsiburada."""
        self.ensure_one()
        self.with_delay(
            channel="root.hepsiburada.product",
            description=_("Sync Hepsiburada brands: %s") % self.name,
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
        """Sync brands from merchant products (HB has no separate brands API).

        Extracts unique brand names from the merchant's product catalog.
        """
        self.ensure_one()
        client = self._get_api_client()
        Brand = self.env["hepsiburada.brand"]

        try:
            # Collect unique brands from merchant product list
            brands_seen = set()
            page = 0
            page_size = 100

            while True:
                result = client.get_products_by_merchant(page=page, size=page_size)
                items = result.get("data") or []
                if not items:
                    break

                for item in items:
                    brand_name = item.get("brand")
                    if brand_name:
                        brands_seen.add(brand_name)

                is_last = result.get("last", True)
                if is_last:
                    break
                page += 1

            brand_list = [{"name": name} for name in brands_seen]
            if brand_list:
                Brand._sync_from_hepsiburada(self, brand_list)

            self.last_brand_sync = fields.Datetime.now()
            _logger.info(
                "Synced %d brands for HB backend %s",
                len(brand_list),
                self.name,
            )
        except HepsiburadaAPIError as e:
            _logger.error("Failed to sync HB brands: %s", str(e))
            raise

    def action_sync_stock_prices(self):
        """Manually trigger stock/price sync."""
        self.ensure_one()
        self.with_delay(
            channel="root.hepsiburada.stock",
            description=_("Sync Hepsiburada stock/prices: %s") % self.name,
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
        """Sync stock and prices to Hepsiburada listing API.

        Sends inventory updates in batches of 100.
        Only sends if stock or price changed since last sync.
        """
        self.ensure_one()
        client = self._get_api_client()
        Binding = self.env["hepsiburada.product.binding"]

        bindings = Binding.search(
            [
                ("backend_id", "=", self.id),
                ("sync_state", "=", "approved"),
            ]
        )

        if not bindings:
            _logger.info("No approved bindings to sync for HB backend %s", self.name)
            return

        items = []
        for binding in bindings:
            item = binding._prepare_stock_price_data()
            if item:
                items.append(item)

        if not items:
            _logger.info("No stock/price changes to sync for HB backend %s", self.name)
            return

        # Send in batches of 100
        batch_size = 100
        total_sent = 0
        for i in range(0, len(items), batch_size):
            batch = items[i : i + batch_size]
            try:
                client.update_listing_inventory(batch)
                total_sent += len(batch)
            except HepsiburadaAPIError:
                _logger.error(
                    "Failed to sync stock/price batch %d for HB backend %s",
                    i // batch_size,
                    self.name,
                    exc_info=True,
                )

        self.last_stock_sync = fields.Datetime.now()
        _logger.info(
            "Synced %d stock/price items for HB backend %s",
            total_sent,
            self.name,
        )

    def action_import_claims(self):
        """Manually trigger claims import."""
        self.ensure_one()
        self.with_delay(
            channel="root.hepsiburada.order",
            description=_("Import Hepsiburada claims: %s") % self.name,
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
        """Import claims/returns from Hepsiburada API."""
        self.ensure_one()
        # TODO: implement when seller account is available
        # client = self._get_api_client()
        # Claim = self.env["hepsiburada.claim"]
        # result = client.get_claims(...)
        # for claim_data in result:
        #     Claim._import_claim(self, claim_data)
        self.last_claim_sync = fields.Datetime.now()
        _logger.info("Imported claims for HB backend %s (stub)", self.name)

    def action_import_questions(self):
        """Manually trigger question import."""
        self.ensure_one()
        self.with_delay(
            channel="root.hepsiburada.order",
            description=_("Import Hepsiburada questions: %s") % self.name,
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
        """Import customer questions from Hepsiburada API."""
        self.ensure_one()
        # TODO: implement when seller account is available
        # client = self._get_api_client()
        # Question = self.env["hepsiburada.question"]
        # result = client.get_questions(...)
        # for question_data in result:
        #     question, is_new = Question._import_question(self, question_data)
        self.last_question_sync = fields.Datetime.now()
        _logger.info("Imported questions for HB backend %s (stub)", self.name)

    def action_import_settlements(self):
        """Manually trigger settlement import."""
        self.ensure_one()
        self.with_delay(
            channel="root.hepsiburada.order",
            description=_("Import Hepsiburada settlements: %s") % self.name,
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
        """Import settlements from Hepsiburada finance API.

        Uses 15-day windows with offset/limit pagination
        (same pattern as Trendyol).
        """
        self.ensure_one()
        client = self._get_api_client()
        Settlement = self.env["hepsiburada.settlement"]

        end_date = fields.Datetime.now()
        if self.last_settlement_sync:
            start_date = self.last_settlement_sync
        else:
            start_date = end_date - timedelta(days=15)

        window_start = start_date
        total_imported = 0

        while window_start < end_date:
            window_end = min(window_start + timedelta(days=15), end_date)

            try:
                offset = 0
                while True:
                    result = client.get_transactions(
                        offset=offset,
                        limit=100,
                        record_date_start=window_start.strftime("%Y-%m-%d"),
                        record_date_end=window_end.strftime("%Y-%m-%d"),
                    )
                    items = (
                        result if isinstance(result, list) else result.get("items", [])
                    )
                    if not items:
                        break

                    for item in items:
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
                        total_imported += 1

                    offset += len(items)
                    if len(items) < 100 or offset > 5000:
                        break

            except HepsiburadaAPIError as e:
                _logger.error(
                    "Failed to import HB settlements for window %s-%s: %s",
                    window_start,
                    window_end,
                    str(e),
                )
                raise

            window_start = window_end

        self.last_settlement_sync = fields.Datetime.now()
        _logger.info(
            "Imported %d settlements for HB backend %s",
            total_imported,
            self.name,
        )

    def action_check_batch_requests(self):
        """Check status of pending batch requests."""
        self.ensure_one()
        self.with_delay(
            channel="root.hepsiburada.product",
            description=_("Check Hepsiburada batch requests: %s") % self.name,
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
        BatchRequest = self.env["hepsiburada.batch.request"]
        pending_requests = BatchRequest.search(
            [
                ("backend_id", "=", self.id),
                ("state", "in", ["pending", "processing"]),
            ]
        )
        for request in pending_requests:
            request._check_status()

    # ==================== Product Import ====================

    def _import_products(self):
        """Import products from Hepsiburada catalog API.

        Paginates through GET /product/api/products/all-products-of-merchant.
        """
        self.ensure_one()
        client = self._get_api_client()

        try:
            page = 0
            page_size = 100
            total_created = 0
            total_skipped = 0

            while True:
                result = client.get_products_by_merchant(page=page, size=page_size)
                items = result.get("data") or []
                _logger.info(
                    "HB product import page %d: %d items, keys: %s",
                    page,
                    len(items),
                    list(result.keys()),
                )
                if items:
                    _logger.info(
                        "HB first item sample: %s",
                        str(items[0])[:500],
                    )
                if not items:
                    break

                for item in items:
                    created = self._import_single_product(item)
                    if created:
                        total_created += 1
                    else:
                        total_skipped += 1

                is_last = result.get("last", True)
                if is_last:
                    break
                page += 1

                if page * page_size >= 5000:
                    _logger.warning(
                        "HB product import safety limit reached at page %d",
                        page,
                    )
                    break

            self.last_product_import_sync = fields.Datetime.now()
            _logger.info(
                "Imported %d products (%d skipped) for HB backend %s",
                total_created,
                total_skipped,
                self.name,
            )
        except HepsiburadaAPIError as e:
            _logger.error("Failed to import HB products: %s", str(e))
            raise

    def _import_single_product(self, item):
        """Import a single product from HB catalog data.

        Returns True if a new binding was created, False if skipped.
        Uses a savepoint so failures don't roll back the entire import.
        """
        hb_sku = (item.get("hepsiburadaSku") or item.get("hbSku") or "").strip()
        merchant_sku = (item.get("merchantSku") or "").strip()

        if not hb_sku:
            return False

        Binding = self.env["hepsiburada.product.binding"]

        # Skip if binding already exists for this SKU + backend
        if Binding.search(
            [("backend_id", "=", self.id), ("hb_sku", "=", hb_sku)],
            limit=1,
        ):
            return False

        try:
            with self.env.cr.savepoint():
                return self._create_product_binding(item, hb_sku, merchant_sku)
        except Exception:
            _logger.error(
                "Failed to import HB product %s: %s",
                hb_sku,
                merchant_sku,
                exc_info=True,
            )
            return False

    def _create_product_binding(self, item, hb_sku, merchant_sku):
        """Create product and binding for an HB catalog item."""
        Binding = self.env["hepsiburada.product.binding"]
        Product = self.env["product.product"]

        # Match existing Odoo product
        barcode = (item.get("barcode") or "").strip()
        product = self._match_product_for_import(merchant_sku, hb_sku, barcode)

        # Check matched product is not already bound to this backend
        if product and Binding.search(
            [("backend_id", "=", self.id), ("odoo_id", "=", product.id)],
            limit=1,
        ):
            return False

        raw_price = item.get("price") or item.get("salePrice") or "0"
        try:
            price = float(raw_price)
        except (ValueError, TypeError):
            price = 0.0

        # Create new product if no match found
        if not product:
            product_name = item.get("productName") or _(
                "[%(sku)s] Hepsiburada Product",
                sku=merchant_sku or hb_sku,
            )
            product = Product.create(
                {
                    "name": product_name,
                    "default_code": merchant_sku or hb_sku,
                    "type": "product",
                    "sale_ok": True,
                    "list_price": price,
                }
            )
            _logger.info(
                "Created new product %s for HB SKU %s",
                product.display_name,
                hb_sku,
            )

        # Resolve brand and category if available
        brand = self._resolve_hb_brand(item.get("brand"))
        category = self._resolve_hb_category(item.get("categoryId"))

        Binding.create(
            {
                "backend_id": self.id,
                "odoo_id": product.id,
                "hb_sku": hb_sku,
                "hb_merchant_sku": merchant_sku or False,
                "hb_sale_price": price,
                "hb_brand_id": brand.id if brand else False,
                "hb_category_id": category.id if category else False,
                "sync_state": "approved",
                "last_sync_date": fields.Datetime.now(),
            }
        )
        return True

    def _match_product_for_import(self, merchant_sku, hb_sku, barcode=""):
        """Match an existing Odoo product by barcode or default_code."""
        Product = self.env["product.product"]
        product = False
        if barcode:
            product = Product.search([("barcode", "=", barcode)], limit=1)
        if not product and merchant_sku:
            product = Product.search([("barcode", "=", merchant_sku)], limit=1)
            if not product:
                product = Product.search([("default_code", "=", merchant_sku)], limit=1)
        if not product and hb_sku:
            product = Product.search([("default_code", "=", hb_sku)], limit=1)
        return product

    def _resolve_hb_brand(self, brand_name):
        """Find HB brand record by name."""
        if not brand_name:
            return False
        return self.env["hepsiburada.brand"].search(
            [("name", "=", brand_name)], limit=1
        )

    def _resolve_hb_category(self, category_id):
        """Find HB category record by HB category ID."""
        if not category_id:
            return False
        return self.env["hepsiburada.category"].search(
            [("hb_category_id", "=", str(category_id))], limit=1
        )

    # ==================== Order Import ====================

    def _import_packages(self, limit=5, offset=0):
        """Import orders from GET /packages/merchantid/{merchantId}.

        Called by the manual 'Import Orders' button with user-supplied
        limit and offset. Each package's lineItems are fed into the
        standard _import_order() routine so the result lands in the
        hepsiburada.order list (the 'Orders' tab).

        Args:
            limit: Number of packages to fetch (clamped to 1–10 by HB API).
            offset: Pagination offset.
        """
        self.ensure_one()
        client = self._get_api_client()

        try:
            result = client.get_packages(offset=offset, limit=limit)
            items = result if isinstance(result, list) else result.get("items") or []

            if not items:
                _logger.info(
                    "No packages found at offset=%d limit=%d for HB backend %s",
                    offset,
                    limit,
                    self.name,
                )
                self.last_order_sync = fields.Datetime.now()
                return

            total_imported = 0
            for item in items:
                try:
                    if self._import_single_package(item):
                        total_imported += 1
                except Exception:
                    _logger.error(
                        "Failed to import HB package %s",
                        item.get("packageNumber") or item.get("id"),
                        exc_info=True,
                    )

            self.last_order_sync = fields.Datetime.now()
            _logger.info(
                "Imported %d packages (offset=%d, limit=%d) for HB backend %s",
                total_imported,
                offset,
                limit,
                self.name,
            )
        except HepsiburadaAPIError as e:
            _logger.error("Failed to import HB packages: %s", str(e))
            raise

    def _parse_hb_datetime(self, value):
        """Parse HB ISO 8601 datetime string to a naive datetime.

        HB uses fractional seconds (e.g. '2026-03-03T09:57:55.494') which
        Odoo's sale.order.create() cannot parse with its default format.
        Returns a naive datetime (microseconds stripped) or now() on failure.
        """
        if not value:
            return fields.Datetime.now()
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", ""))
            return dt.replace(tzinfo=None, microsecond=0)
        except (ValueError, TypeError):
            _logger.warning("Could not parse HB datetime %r, using now()", value)
            return fields.Datetime.now()

    def _import_single_package(self, item):
        """Import one package by fetching full order details and delegating
        to hepsiburada.order._import_order().

        The packages endpoint returns shipping-level data without full
        product lines. We extract order numbers, call get_order_detail()
        for the full line items, and route through the standard import path.

        Returns the hepsiburada.order binding, or False if skipped.
        """
        self.ensure_one()
        Order = self.env["hepsiburada.order"]

        package_number = str(item.get("packageNumber") or item.get("id") or "")
        if not package_number:
            _logger.warning("HB package item has no packageNumber/id, skipping")
            return False

        # Extract order numbers from the package's line items
        line_items = item.get("items") or []
        order_numbers = {
            str(li.get("orderNumber") or "")
            for li in line_items
            if li.get("orderNumber")
        }

        if not order_numbers:
            # Fallback: try orderNumber at the package level
            order_number = str(item.get("orderNumber") or "")
            if order_number:
                order_numbers = {order_number}
            else:
                _logger.warning(
                    "HB package %s has no orderNumber, skipping",
                    package_number,
                )
                return False

        client = self._get_api_client()
        imported = False

        for order_number in order_numbers:
            # Skip if already imported
            if Order.search(
                [
                    ("backend_id", "=", self.id),
                    ("hb_order_number", "=", order_number),
                ],
                limit=1,
            ):
                continue

            # Fetch full order detail with line items
            try:
                detail = client.get_order_detail(order_number)
            except HepsiburadaAPIError:
                _logger.error(
                    "Failed to fetch order detail for %s, skipping",
                    order_number,
                    exc_info=True,
                )
                continue

            # get_order_detail returns line items in the same format
            detail_items = detail.get("items", [])
            if not detail_items:
                detail_items = detail if isinstance(detail, list) else []

            if not detail_items:
                _logger.warning(
                    "No line items in order detail for %s, skipping",
                    order_number,
                )
                continue

            try:
                binding = Order._import_order(self, detail_items)
                if binding:
                    # Set package number if not already set
                    if package_number and not binding.hb_package_number:
                        binding.hb_package_number = package_number
                    imported = binding
            except Exception:
                _logger.error(
                    "Failed to import HB order %s from package %s",
                    order_number,
                    package_number,
                    exc_info=True,
                )

        return imported

    def _import_orders(self):
        """Import paid orders from Hepsiburada API.

        Paginates through GET /orders/merchantid/{merchantId}.
        Groups line items by orderNumber and delegates to
        hepsiburada.order._import_order().
        Uses last_order_sync for date filtering (same as Trendyol).
        """
        self.ensure_one()
        client = self._get_api_client()
        Order = self.env["hepsiburada.order"]

        # Calculate date range (same pattern as Trendyol)
        end_date = fields.Datetime.now()
        if self.last_order_sync:
            start_date = self.last_order_sync
        else:
            # First sync: get last 7 days
            start_date = end_date - timedelta(days=7)

        begin_date_str = start_date.strftime("%Y-%m-%d %H:%M")
        end_date_str = end_date.strftime("%Y-%m-%d %H:%M")

        try:
            offset = 0
            total_imported = 0
            # Use a dict to group line items by orderNumber
            orders_by_number = {}

            while True:
                result = client.get_paid_orders(
                    offset=offset,
                    limit=10,
                    begin_date=begin_date_str,
                    end_date=end_date_str,
                )
                items = result.get("items", [])
                if not items:
                    break

                for item in items:
                    order_number = item.get("orderNumber")
                    if not order_number:
                        _logger.warning(
                            "Skipping HB line item without orderNumber: %s",
                            item.get("id"),
                        )
                        continue
                    orders_by_number.setdefault(order_number, []).append(item)

                offset += len(items)
                # Safety limit: max 500 items per import run
                if offset >= 500:
                    _logger.warning("HB order import safety limit reached")
                    break

            # Import grouped orders
            for order_number, line_items in orders_by_number.items():
                try:
                    Order._import_order(self, line_items)
                    total_imported += 1
                except Exception:
                    _logger.error(
                        "Failed to import HB order %s",
                        order_number,
                        exc_info=True,
                    )
                    continue

            self.last_order_sync = fields.Datetime.now()
            _logger.info(
                "Imported %d orders for HB backend %s",
                total_imported,
                self.name,
            )
        except HepsiburadaAPIError as e:
            _logger.error("Failed to import HB orders: %s", str(e))
            raise

    def _sync_cancelled_orders(self):
        """Poll cancelled orders endpoint, update HB order status."""
        self.ensure_one()
        client = self._get_api_client()
        Order = self.env["hepsiburada.order"]

        try:
            offset = 0
            total_cancelled = 0
            while True:
                result = client.get_cancelled_orders(offset=offset, limit=50)
                items = result.get("items", [])
                if not items:
                    break

                for item in items:
                    order_number = item.get("orderNumber")
                    line_item_id = item.get("id")
                    if not order_number or not line_item_id:
                        continue

                    # Find existing binding
                    order = Order.search(
                        [
                            ("backend_id", "=", self.id),
                            ("hb_order_number", "=", str(order_number)),
                        ],
                        limit=1,
                    )
                    if order and order.hb_status != "cancelled":
                        order.hb_status = "cancelled"
                        # Cancel Odoo sale order
                        if order.odoo_id.state not in ("done", "cancel"):
                            order.odoo_id.with_context(
                                from_hb_cancel=True,
                                disable_cancel_warning=True,
                            ).action_cancel()
                        total_cancelled += 1

                offset += len(items)
                if offset >= 2500:
                    _logger.warning("HB cancelled orders safety limit reached")
                    break

            _logger.info(
                "Processed %d cancellations for HB backend %s",
                total_cancelled,
                self.name,
            )
        except HepsiburadaAPIError as e:
            _logger.error("Failed to sync HB cancelled orders: %s", str(e))
            raise

    # ==================== Cron Methods ====================

    @api.model
    def _cron_import_orders(self):
        """Cron job to import orders from all active backends."""
        backends = self.search(
            [("active", "=", True), ("auto_import_orders", "=", True)]
        )
        for backend in backends:
            backend.with_delay(
                channel="root.hepsiburada.order",
                description=_("Import Hepsiburada orders: %s") % backend.name,
            )._import_orders()

    @api.model
    def _cron_sync_cancelled_orders(self):
        """Cron job to sync cancelled orders from all active backends."""
        backends = self.search(
            [("active", "=", True), ("auto_import_orders", "=", True)]
        )
        for backend in backends:
            backend.with_delay(
                channel="root.hepsiburada.order",
                description=_("Sync Hepsiburada cancelled orders: %s") % backend.name,
            )._sync_cancelled_orders()

    @api.model
    def _cron_import_claims(self):
        """Cron job to import claims from all active backends."""
        backends = self.search(
            [("active", "=", True), ("auto_import_claims", "=", True)]
        )
        for backend in backends:
            backend.with_delay(
                channel="root.hepsiburada.order",
                description=_("Import Hepsiburada claims: %s") % backend.name,
            )._import_claims()

    @api.model
    def _cron_import_questions(self):
        """Cron job to import questions from all active backends."""
        backends = self.search(
            [("active", "=", True), ("auto_import_questions", "=", True)]
        )
        for backend in backends:
            backend.with_delay(
                channel="root.hepsiburada.order",
                description=_("Import Hepsiburada questions: %s") % backend.name,
            )._import_questions()

    @api.model
    def _cron_import_settlements(self):
        """Cron job to import settlements from all active backends."""
        backends = self.search(
            [("active", "=", True), ("auto_import_settlements", "=", True)]
        )
        for backend in backends:
            backend.with_delay(
                channel="root.hepsiburada.order",
                description=_("Import Hepsiburada settlements: %s") % backend.name,
            )._import_settlements()

    @api.model
    def _cron_send_invoices(self):
        """Cron job to send pending invoices for all active backends."""
        backends = self.search(
            [("active", "=", True), ("auto_send_invoice", "=", True)]
        )
        for backend in backends:
            backend._send_pending_invoices()

    def _send_pending_invoices(self):
        """Find orders with posted invoices and queue invoice sending.

        Same pattern as Trendyol: search orders where invoice_link_sent=False,
        check if a posted invoice exists, then queue _send_invoice().
        """
        self.ensure_one()
        orders = self.env["hepsiburada.order"].search(
            [
                ("backend_id", "=", self.id),
                ("invoice_link_sent", "=", False),
                ("hb_status", "!=", "cancelled"),
            ]
        )
        queued = 0
        for order in orders:
            # Check if there's a posted invoice
            has_invoice = order.odoo_id.invoice_ids.filtered(
                lambda i: i.state == "posted" and i.move_type == "out_invoice"
            )
            if has_invoice:
                order.with_delay(
                    channel="root.hepsiburada.order",
                    description=_("Send invoice: %s") % order.hb_order_number,
                )._send_invoice()
                queued += 1

        if queued:
            _logger.info(
                "Queued %d invoice sends for HB backend %s",
                queued,
                self.name,
            )

    @api.model
    def _cron_sync_stock_prices(self):
        """Cron job to sync stock/prices for all active backends."""
        backends = self.search([("active", "=", True), ("auto_sync_stock", "=", True)])
        for backend in backends:
            backend.with_delay(
                channel="root.hepsiburada.stock",
                description=_("Sync Hepsiburada stock/prices: %s") % backend.name,
            )._sync_stock_prices()

    @api.model
    def _cron_check_batch_requests(self):
        """Cron job to check batch request status for all active backends."""
        backends = self.search([("active", "=", True)])
        for backend in backends:
            backend.with_delay(
                channel="root.hepsiburada.product",
                description=_("Check Hepsiburada batch requests: %s") % backend.name,
            )._check_batch_requests()

    @api.model
    def _cron_sync_metadata(self):
        """Cron job to sync categories and brands for all active backends."""
        backends = self.search([("active", "=", True)])
        for backend in backends:
            backend.with_delay(
                channel="root.hepsiburada.product",
                description=_("Sync Hepsiburada metadata: %s") % backend.name,
            )._sync_categories()
            backend.with_delay(
                channel="root.hepsiburada.product",
                description=_("Sync Hepsiburada brands: %s") % backend.name,
            )._sync_brands()
