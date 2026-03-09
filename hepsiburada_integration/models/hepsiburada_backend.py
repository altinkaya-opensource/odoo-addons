# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import logging
from datetime import timedelta

from dateutil import parser as dateutil_parser

from odoo import _, api, fields, models

from .hepsiburada_request import HepsiburadaAPIError, HepsiburadaRequest

_logger = logging.getLogger(__name__)


def _parse_hb_datetime(dt_string):
    """Parse a Hepsiburada datetime string to naive UTC datetime.

    HB sends ISO 8601 strings like '2026-01-15T10:30:00'.
    Returns False if the input is falsy or unparseable.
    """
    if not dt_string:
        return False
    try:
        dt = dateutil_parser.isoparse(str(dt_string))
        if dt.tzinfo:
            from datetime import UTC

            dt = dt.astimezone(UTC).replace(tzinfo=None)
        return dt
    except (ValueError, TypeError):
        return False


class HepsiburadaBackend(models.Model):
    _name = "hepsiburada.backend"
    _description = "Hepsiburada Backend Configuration"
    _inherit = ["marketplace.backend"]

    # API Credentials
    merchant_id = fields.Char(
        string="Merchant ID",
        required=True,
        tracking=True,
        help="Your Hepsiburada merchant ID",
    )
    api_username = fields.Char(
        string="API Username",
        required=True,
        groups="hepsiburada_integration.group_hepsiburada_manager",
    )
    api_password = fields.Char(
        string="API Password",
        required=True,
        groups="hepsiburada_integration.group_hepsiburada_manager",
    )
    user_agent = fields.Char(
        string="User-Agent",
        required=True,
        help="User-Agent header sent with every API request to Hepsiburada",
    )

    # Cargo mappings
    cargo_mapping_ids = fields.One2many(
        "hepsiburada.cargo.mapping",
        "backend_id",
        string="Cargo Mappings",
        help="Map Hepsiburada cargo providers to Odoo delivery carriers",
    )

    # Settlement partner
    hb_partner_id = fields.Many2one(
        "res.partner",
        string="Hepsiburada Partner",
        help="Partner record for Hepsiburada. Used for commission "
        "settlement payments and for reporting purposes.",
    )

    # Last Sync Timestamps (Hepsiburada-specific)
    last_category_sync = fields.Datetime(
        readonly=True,
    )
    last_brand_sync = fields.Datetime(
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
    settlement_count = fields.Integer(
        compute="_compute_counts",
        string="Settlements",
    )
    question_count = fields.Integer(
        compute="_compute_counts",
        string="Questions",
    )
    claim_count = fields.Integer(
        compute="_compute_counts",
        string="Claims",
    )

    @api.depends()
    def _compute_counts(self):
        ProductBinding = self.env["hepsiburada.product.binding"]
        Order = self.env["hepsiburada.order"]
        Settlement = self.env["hepsiburada.settlement"]
        Question = self.env["hepsiburada.question"]
        Claim = self.env["hepsiburada.claim"]
        for backend in self:
            backend.product_binding_count = ProductBinding.search_count(
                [("backend_id", "=", backend.id)]
            )
            backend.order_count = Order.search_count([("backend_id", "=", backend.id)])
            backend.settlement_count = Settlement.search_count(
                [("backend_id", "=", backend.id)]
            )
            backend.question_count = Question.search_count(
                [("backend_id", "=", backend.id)]
            )
            backend.claim_count = Claim.search_count([("backend_id", "=", backend.id)])

    # ==================== Hook Implementations ====================

    def _get_api_client(self):
        """Get configured API client for this backend."""
        self.ensure_one()
        return HepsiburadaRequest(
            merchant_id=self.merchant_id,
            username=self.api_username,
            password=self.api_password,
            environment=self.environment,
            user_agent=self.user_agent,
        )

    def _get_marketplace_partner(self):
        """Return the Hepsiburada partner for commission payments."""
        self.ensure_one()
        return self.hb_partner_id or False

    def _get_cargo_mappings(self):
        """Return cargo mapping recordset."""
        self.ensure_one()
        return self.cargo_mapping_ids

    def _get_cargo_mapping_name(self, mapping):
        """Get cargo provider name from a mapping record."""
        return mapping.hepsiburada_cargo_provider_name

    # ==================== Order Import ====================

    def action_import_orders(self):
        """Manually trigger order import."""
        self.ensure_one()
        self.with_delay(
            channel="root.hepsiburada.order",
            description=_("Import Hepsiburada orders: %s") % self.name,
        )._import_orders()
        return self._build_notification(
            _("Import Started"),
            _("Order import has been queued."),
        )

    def _fetch_all_packages(self, fetch_method):
        """Paginate through a package endpoint until exhausted.

        Args:
            fetch_method: API client method (e.g. client.get_packages)

        Returns:
            List of package dicts
        """
        all_packages = []
        offset = 0
        limit = 50

        while True:
            result = fetch_method(offset=offset, limit=limit)
            packages = (
                result
                if isinstance(result, list)
                else result.get("items", result.get("content", []))
            )
            if not packages:
                break
            all_packages.extend(packages)
            offset += limit
            if offset > 5000:
                _logger.warning("Import safety limit reached")
                break

        return all_packages

    @staticmethod
    def _normalize_order_item(item):
        """Normalize a flat /orders line item to match /packages format.

        The /orders endpoint uses different field names and nested structures
        compared to /packages.  This converts the item in-place so the rest
        of the import pipeline can work with a single format.
        """
        # lineItemId ← id
        if "lineItemId" not in item and "id" in item:
            item["lineItemId"] = item["id"]

        # merchantSku ← merchantSKU
        if "merchantSku" not in item and "merchantSKU" in item:
            item["merchantSku"] = item["merchantSKU"]

        # hbSku ← sku
        if "hbSku" not in item and "sku" in item:
            item["hbSku"] = item["sku"]

        # price ← unitPrice (both are {currency, amount} objects)
        if "price" not in item and "unitPrice" in item:
            item["price"] = item["unitPrice"]
        if "merchantUnitPrice" not in item and "unitPrice" in item:
            item["merchantUnitPrice"] = item["unitPrice"]

        # unitHBDiscount ← hbDiscount.unitPrice
        hb_disc = item.get("hbDiscount", {})
        if "unitHBDiscount" not in item and isinstance(hb_disc, dict):
            item["unitHBDiscount"] = hb_disc.get("unitPrice", {})

        # unitMerchantDiscount ← merchantDiscount.unitPrice
        m_disc = item.get("merchantDiscount", {})
        if "unitMerchantDiscount" not in item and isinstance(m_disc, dict):
            item["unitMerchantDiscount"] = m_disc.get("unitPrice", {})

        return item

    def _group_flat_items_as_packages(self, flat_items, hb_status, api_status):
        """Group flat order line items by orderNumber into pseudo-package dicts.

        Args:
            flat_items: List of flat line-item dicts from HB /orders endpoints
            hb_status: Internal status tag (e.g. "open", "payment_awaiting")
            api_status: Original HB status string (e.g. "Open", "PaymentAwaiting")

        Returns:
            List of pseudo-package dicts in /packages-compatible format
        """
        by_number = {}
        for item in flat_items:
            self._normalize_order_item(item)
            order_number = str(item.get("orderNumber", ""))
            if order_number:
                by_number.setdefault(order_number, []).append(item)

        packages = []
        for _order_number, items in by_number.items():
            first = items[0]

            # Extract package-level fields from nested structures
            shipping = first.get("shippingAddress", {})
            invoice = first.get("invoice", {})
            billing_addr = invoice.get("address", {})

            packages.append(
                {
                    "items": items,
                    "customerName": first.get("customerName", ""),
                    "customerId": first.get("customerId", ""),
                    "orderDate": first.get("orderDate", ""),
                    "dueDate": first.get("dueDate", ""),
                    "cargoCompany": first.get("cargoCompany", ""),
                    "packageNumber": first.get("packageNumber", ""),
                    "barcode": first.get("barcode", ""),
                    # Billing / invoice fields
                    "taxNumber": invoice.get("taxNumber", ""),
                    "identityNo": invoice.get("turkishIdentityNumber", ""),
                    "taxOffice": invoice.get("taxOffice", ""),
                    "billingAddress": billing_addr.get("address", ""),
                    "billingCity": billing_addr.get("city", ""),
                    "billingDistrict": billing_addr.get("district", ""),
                    "billingTown": billing_addr.get("town", ""),
                    "billingPostalCode": billing_addr.get("postalCode", ""),
                    "billingCountryCode": billing_addr.get("countryCode", "TR"),
                    # Shipping fields
                    "recipientName": shipping.get("name", ""),
                    "shippingAddressDetail": shipping.get("address", ""),
                    "shippingCity": shipping.get("city", ""),
                    "shippingDistrict": shipping.get("district", ""),
                    "shippingTown": shipping.get("town", ""),
                    "shippingCountryCode": shipping.get("countryCode", "TR"),
                    # Contact
                    "email": shipping.get("email", "") or billing_addr.get("email", ""),
                    "phoneNumber": shipping.get("phoneNumber", ""),
                    # Status
                    "status": api_status,
                    "_hb_status": hb_status,
                }
            )
        return packages

    def _import_orders(self):
        """Import orders from all Hepsiburada endpoints."""
        self.ensure_one()
        client = self._get_api_client()
        Order = self.env["hepsiburada.order"]

        try:
            all_packages = []

            # 1. Flat order endpoints → group into pseudo-packages
            flat_endpoints = [
                (client.get_paid_orders, "open", "Open"),
                (
                    client.get_payment_awaiting_orders,
                    "payment_awaiting",
                    "PaymentAwaiting",
                ),
            ]
            for fetch_method, hb_status, api_status in flat_endpoints:
                try:
                    flat_items = self._fetch_all_packages(fetch_method)
                    all_packages.extend(
                        self._group_flat_items_as_packages(
                            flat_items, hb_status, api_status
                        )
                    )
                except HepsiburadaAPIError:
                    _logger.exception("Failed to fetch %s orders", hb_status)

            # 2. Package endpoints (already in package format)
            package_endpoints = [
                (client.get_packages, "packaged"),
                (client.get_shipped_packages, "in_transit"),
                (client.get_delivered_packages, "delivered"),
                (client.get_undelivered_packages, "undelivered"),
                (client.get_cancelled_packages, "cancelled"),
            ]

            for fetch_method, status in package_endpoints:
                try:
                    packages = self._fetch_all_packages(fetch_method)
                    for pkg in packages:
                        pkg["_hb_status"] = status
                    all_packages.extend(packages)
                except HepsiburadaAPIError:
                    _logger.exception("Failed to fetch %s packages", status)

            if not all_packages:
                _logger.info("No packages to import for backend %s", self.name)
                self.last_order_sync = fields.Datetime.now()
                return

            total_imported = 0
            for package_data in all_packages:
                items = package_data.get("items", [])
                if not items:
                    continue
                order_number = str(items[0].get("orderNumber", ""))
                try:
                    Order._import_order(self, package_data)
                    total_imported += 1
                except Exception:
                    _logger.exception("Failed to import HB order %s", order_number)

            self.last_order_sync = fields.Datetime.now()
            _logger.info(
                "Imported %d orders for backend %s",
                total_imported,
                self.name,
            )
        except HepsiburadaAPIError as e:
            _logger.error("Failed to import orders: %s", str(e))
            raise

    def action_import_cancelled_orders(self):
        """Manually trigger cancelled order status update."""
        self.ensure_one()
        self.with_delay(
            channel="root.hepsiburada.order",
            description=_("Import HB cancelled orders: %s") % self.name,
        )._import_cancelled_orders()
        return self._build_notification(
            _("Import Started"),
            _("Cancelled order sync has been queued."),
        )

    def _import_cancelled_orders(self):
        """Import cancelled packages to update existing order statuses."""
        self.ensure_one()
        client = self._get_api_client()
        Order = self.env["hepsiburada.order"]

        try:
            packages = self._fetch_all_packages(client.get_cancelled_packages)
            total_updated = 0

            for pkg in packages:
                items = pkg.get("items", [])
                if not items:
                    continue
                order_number = str(items[0].get("orderNumber", ""))
                if not order_number:
                    continue
                existing = Order.search(
                    [
                        ("backend_id", "=", self.id),
                        ("hb_order_number", "=", order_number),
                    ],
                    limit=1,
                )
                if existing and existing.hb_status != "cancelled":
                    existing.hb_status = "cancelled"
                    existing._update_picking_delivery_state("cancelled")
                    if existing.odoo_id.state not in ("done", "cancel"):
                        existing.odoo_id.with_context(
                            from_hepsiburada_cancel=True,
                            disable_cancel_warning=True,
                        ).action_cancel()
                    total_updated += 1

            _logger.info(
                "Updated %d cancelled orders for backend %s",
                total_updated,
                self.name,
            )
        except HepsiburadaAPIError as e:
            _logger.error("Failed to import cancelled orders: %s", str(e))
            raise

    # ==================== Settlement Import ====================

    def action_import_settlements(self):
        """Manually trigger settlement import."""
        self.ensure_one()
        self.with_delay(
            channel="root.hepsiburada.order",
            description=_("Import Hepsiburada settlements: %s") % self.name,
        )._import_settlements()
        return self._build_notification(
            _("Import Started"),
            _("Settlement import has been queued."),
        )

    def _import_settlements(self):
        """Import settlements from Hepsiburada finance API.

        The API has a max 15-day date range. We iterate in 15-day windows
        from last_settlement_sync (or 15 days ago) to now.
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
            start_str = window_start.strftime("%Y-%m-%d")
            end_str = window_end.strftime("%Y-%m-%d")

            try:
                offset = 0
                while True:
                    result = client.get_transactions(
                        record_date_start=start_str,
                        record_date_end=end_str,
                        transaction_types="Payment,Return,Commission",
                        offset=offset,
                        limit=100,
                    )
                    content = (
                        result
                        if isinstance(result, list)
                        else result.get("content", result.get("items", []))
                    )
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
                                    settlement.hb_transaction_id,
                                    str(e),
                                )
                        total_imported += 1

                    offset += 100
                    if offset > 5000:
                        _logger.warning("Settlement import safety limit reached")
                        break

            except HepsiburadaAPIError as e:
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

    # ==================== View Actions ====================

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

    # ==================== Claim Import ====================

    def action_import_claims(self):
        """Manually trigger claim import."""
        self.ensure_one()
        self.with_delay(
            channel="root.hepsiburada.order",
            description=_("Import Hepsiburada claims: %s") % self.name,
        )._import_claims()
        return self._build_notification(
            _("Import Started"),
            _("Claim import has been queued."),
        )

    def _import_claims(self):
        """Import customer claims from Hepsiburada OMS API."""
        self.ensure_one()
        client = self._get_api_client()
        Claim = self.env["hepsiburada.claim"]

        total_imported = 0
        offset = 0

        while True:
            try:
                result = client.get_claims(offset=offset, limit=50)
            except HepsiburadaAPIError as e:
                _logger.error("Failed to fetch claims at offset %d: %s", offset, e)
                raise

            claims = (
                result
                if isinstance(result, list)
                else result.get("items", result.get("content", []))
            )
            if not claims:
                break

            for claim_data in claims:
                try:
                    Claim._import_claim(self, claim_data)
                    total_imported += 1
                except Exception:
                    _logger.exception(
                        "Failed to import claim %s",
                        claim_data.get("claimNumber", "?"),
                    )

            offset += 50
            if offset > 5000:
                _logger.warning("Claim import safety limit reached")
                break

        self.last_claim_sync = fields.Datetime.now()
        _logger.info("Imported %d claims for backend %s", total_imported, self.name)

    # ==================== Question Import ====================

    def action_import_questions(self):
        """Manually trigger question import."""
        self.ensure_one()
        self.with_delay(
            channel="root.hepsiburada.order",
            description=_("Import Hepsiburada questions: %s") % self.name,
        )._import_questions()
        return self._build_notification(
            _("Import Started"),
            _("Question import has been queued."),
        )

    def _import_questions(self):
        """Import customer questions from Hepsiburada AskToSeller API."""
        self.ensure_one()
        client = self._get_api_client()
        Question = self.env["hepsiburada.question"]

        total_imported = 0
        current_page = 1

        while True:
            try:
                result = client.get_issues(current_page=current_page, page_size=50)
            except HepsiburadaAPIError as e:
                _logger.error("Failed to fetch questions page %d: %s", current_page, e)
                raise

            issues = result.get("data", result.get("items", []))
            if not issues:
                break

            for issue_data in issues:
                try:
                    question = Question._import_question(self, issue_data)
                    if question:
                        # Conversations may be inline in list response
                        convs = issue_data.get("conversations", [])
                        if convs:
                            question._import_conversations(convs)
                        else:
                            question._import_conversations()
                        total_imported += 1
                except Exception:
                    _logger.exception(
                        "Failed to import question %s",
                        issue_data.get("number", "?"),
                    )

            total_pages = result.get("totalPageCount", 1)
            if current_page >= total_pages:
                break
            current_page += 1

        self.last_question_sync = fields.Datetime.now()
        _logger.info("Imported %d questions for backend %s", total_imported, self.name)

    # ==================== Catalog Sync ====================

    def action_sync_categories(self):
        """Sync categories from Hepsiburada."""
        self.ensure_one()
        self.with_delay(
            channel="root.hepsiburada.product",
            description=_("Sync Hepsiburada categories: %s") % self.name,
        )._sync_categories()
        return self._build_notification(
            _("Sync Started"),
            _("Category synchronization has been queued."),
        )

    def _sync_categories(self):
        """Sync leaf categories from Hepsiburada API with pagination."""
        self.ensure_one()
        client = self._get_api_client()
        Category = self.env["hepsiburada.category"]

        try:
            page = 0
            total_synced = 0
            while True:
                result = client.get_categories(leaf=True, page=page, size=1000)
                categories = (
                    result
                    if isinstance(result, list)
                    else result.get("data", result.get("categories", []))
                )
                if not categories:
                    break
                Category._sync_from_hepsiburada(self, categories)
                total_synced += len(categories)
                # Check if there are more pages
                total_pages = 1
                if isinstance(result, dict):
                    total_pages = result.get("totalPages", 1)
                if page + 1 >= total_pages:
                    break
                page += 1

            self.last_category_sync = fields.Datetime.now()
            _logger.info(
                "Synced %d leaf categories for backend %s",
                total_synced,
                self.name,
            )
        except HepsiburadaAPIError as e:
            _logger.error("Failed to sync categories: %s", str(e))
            raise

    def action_sync_brands(self):
        """Sync brands from Hepsiburada."""
        self.ensure_one()
        self.with_delay(
            channel="root.hepsiburada.product",
            description=_("Sync Hepsiburada brands: %s") % self.name,
        )._sync_brands()
        return self._build_notification(
            _("Sync Started"),
            _("Brand synchronization has been queued."),
        )

    def _sync_brands(self):
        """Sync brands from Hepsiburada API.

        Note: Hepsiburada does not have a separate brands endpoint.
        Brands are typically part of category attributes.
        This method is a placeholder for manual brand import.
        """
        self.ensure_one()
        self.last_brand_sync = fields.Datetime.now()
        _logger.info("Brand sync completed for backend %s", self.name)

    def action_view_products(self):
        """View product bindings for this backend."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Product Bindings"),
            "res_model": "hepsiburada.product.binding",
            "view_mode": "tree,form",
            "domain": [("backend_id", "=", self.id)],
            "context": {"default_backend_id": self.id},
        }

    def action_open_batch_export_wizard(self):
        """Open the batch export wizard."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Batch Export to Hepsiburada"),
            "res_model": "hepsiburada.batch.export.wizard",
            "view_mode": "form",
            "target": "new",
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
                channel="root.hepsiburada.order",
                description=_("Import Hepsiburada orders: %s") % backend.name,
            )._import_orders()

    @api.model
    def _cron_import_cancelled_orders(self):
        """Cron job to sync cancelled orders from all active backends."""
        backends = self.search(
            [
                ("active", "=", True),
                ("auto_import_orders", "=", True),
            ]
        )
        for backend in backends:
            backend.with_delay(
                channel="root.hepsiburada.order",
                description=_("Sync HB cancelled orders: %s") % backend.name,
            )._import_cancelled_orders()

    @api.model
    def _cron_send_invoices(self):
        """Cron job to sync missing invoices and send invoice links."""
        backends = self.search(
            [
                ("active", "=", True),
                ("auto_send_invoice", "=", True),
            ]
        )
        for backend in backends:
            backend.with_delay(
                channel="root.hepsiburada.order",
                description=_("Sync missing invoices: %s") % backend.name,
            )._sync_missing_invoices()
            backend._send_pending_invoices()

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
                channel="root.hepsiburada.order",
                description=_("Import Hepsiburada settlements: %s") % backend.name,
            )._import_settlements()

    @api.model
    def _cron_import_questions(self):
        """Cron job to import questions from all active backends."""
        backends = self.search(
            [
                ("active", "=", True),
                ("auto_import_questions", "=", True),
            ]
        )
        for backend in backends:
            backend.with_delay(
                channel="root.hepsiburada.order",
                description=_("Import Hepsiburada questions: %s") % backend.name,
            )._import_questions()

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
                channel="root.hepsiburada.order",
                description=_("Import Hepsiburada claims: %s") % backend.name,
            )._import_claims()

    def _send_pending_invoices(self):
        """Find Hepsiburada orders with pending invoices and queue sends."""
        self.ensure_one()
        orders = self.env["hepsiburada.order"].search(
            [
                ("backend_id", "=", self.id),
                ("invoice_link_sent", "=", False),
                ("hb_status", "!=", "cancelled"),
            ]
        )
        for order in orders:
            posted_invoice = order.odoo_id.invoice_ids.filtered(
                lambda i: i.state == "posted" and i.move_type == "out_invoice"
            )
            if not posted_invoice:
                continue
            order.with_delay(
                channel="root.hepsiburada.order",
                description=_("Send invoice: %s") % order.hb_order_number,
            )._send_invoice()

    # ==================== Missing Invoice Sync ====================

    def action_sync_missing_invoices(self):
        """Manually trigger missing invoice sync."""
        self.ensure_one()
        self.with_delay(
            channel="root.hepsiburada.order",
            description=_("Sync missing invoices: %s") % self.name,
        )._sync_missing_invoices()
        return self._build_notification(
            _("Sync Started"),
            _("Missing invoice sync has been queued."),
        )

    def _sync_missing_invoices(self):
        """Fetch packages with missing invoices from HB and mark orders."""
        self.ensure_one()
        client = self._get_api_client()
        Order = self.env["hepsiburada.order"]

        # Collect all package numbers that HB reports as missing invoice
        missing_package_numbers = set()
        missing_order_numbers = set()
        offset = 0

        while True:
            try:
                result = client.get_missing_invoice_packages(offset=offset, limit=50)
            except HepsiburadaAPIError as e:
                _logger.error(
                    "Failed to fetch missing invoices at offset %d: %s",
                    offset,
                    e,
                )
                raise

            items = result if isinstance(result, list) else result.get("items", [])
            if not items:
                break

            for item in items:
                pkg_number = item.get("packageNumber", "")
                if pkg_number:
                    missing_package_numbers.add(str(pkg_number))
                for order_num in item.get("orderNumbers", []):
                    if order_num:
                        missing_order_numbers.add(str(order_num))

            total_count = result.get("totalCount", 0) if isinstance(result, dict) else 0
            offset += 50
            if offset >= total_count or offset > 5000:
                break

        # Build domain to find matching orders
        domain_parts = []
        if missing_package_numbers:
            domain_parts.append(
                ("hb_package_number", "in", list(missing_package_numbers))
            )
        if missing_order_numbers:
            domain_parts.append(("hb_order_number", "in", list(missing_order_numbers)))

        if domain_parts:
            # Combine with OR if both exist
            search_domain = [("backend_id", "=", self.id)]
            if len(domain_parts) == 2:
                search_domain += ["|"] + domain_parts
            else:
                search_domain += domain_parts

            orders_to_mark = Order.search(search_domain)
            orders_to_mark.filtered(lambda o: not o.hb_missing_invoice).write(
                {"hb_missing_invoice": True}
            )

            # Clear flag for orders no longer in the missing list
            orders_to_clear = Order.search(
                [
                    ("backend_id", "=", self.id),
                    ("hb_missing_invoice", "=", True),
                    ("id", "not in", orders_to_mark.ids),
                ]
            )
            if orders_to_clear:
                orders_to_clear.write({"hb_missing_invoice": False})
        else:
            # No missing invoices — clear all flags
            Order.search(
                [
                    ("backend_id", "=", self.id),
                    ("hb_missing_invoice", "=", True),
                ]
            ).write({"hb_missing_invoice": False})

        _logger.info(
            "Missing invoice sync done for backend %s: %d packages missing",
            self.name,
            len(missing_package_numbers) + len(missing_order_numbers),
        )
