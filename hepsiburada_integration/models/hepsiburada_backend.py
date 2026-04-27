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
    _inherit = ["marketplace.backend.mixin", "mail.thread", "mail.activity.mixin"]

    name = fields.Char(required=True, tracking=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
    )

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
        help="Warehouses to use for order fulfillment",
    )
    pricelist_id = fields.Many2one(
        "product.pricelist",
        required=True,
        help="Pricelist to use for Hepsiburada prices (must be in TRY)",
    )
    sales_team_id = fields.Many2one(
        "crm.team",
        help="Default sales team for Hepsiburada orders",
    )
    fiscal_position_id = fields.Many2one(
        "account.fiscal.position",
        help="Default fiscal position for Hepsiburada orders",
    )
    source_id = fields.Many2one(
        "utm.source",
        help="UTM source to set on Hepsiburada orders",
    )

    # Default Settings
    default_cargo_company_id = fields.Many2one(
        "delivery.carrier",
        help="Default delivery carrier for Hepsiburada orders",
    )
    cargo_mapping_ids = fields.One2many(
        "hepsiburada.cargo.mapping",
        "backend_id",
        string="Cargo Mappings",
        help="Map Hepsiburada cargo providers to Odoo delivery carriers",
    )
    default_product_id = fields.Many2one(
        "product.product",
        help="Fallback product for unmapped items. "
        "If not set, unmapped items will be created as note lines.",
    )
    user_agent = fields.Char(
        string="User-Agent",
        required=True,
        help="User-Agent header sent with every API request to Hepsiburada",
    )

    label_printer_id = fields.Many2one(
        "printing.printer",
        help="Default printer for Hepsiburada shipping labels (Ortak Barkod). "
        "Used when the delivery carrier has no printer configured.",
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
    auto_sync_tracking = fields.Boolean(
        default=True,
        help="Automatically send tracking numbers when delivery is done",
    )
    auto_send_invoice = fields.Boolean(
        default=True,
        help="Send invoice links to Hepsiburada via nightly batch cron",
    )

    # Settlement / Accounting
    hb_partner_id = fields.Many2one(
        "res.partner",
        string="Hepsiburada Partner",
        help="Partner record for Hepsiburada. Used for commission "
        "settlement payments and for reporting purposes.",
    )
    settlement_journal_id = fields.Many2one(
        "account.journal",
        string="Hepsiburada Payment Journal",
        domain="[('type', '=', 'bank')]",
        help="Intermediary bank-type journal for Hepsiburada payments. "
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

    # Questions
    auto_import_questions = fields.Boolean(
        default=True,
        help="Automatically import customer questions via scheduled job",
    )

    # Claims
    auto_import_claims = fields.Boolean(
        default=True,
        help="Automatically import customer claims via scheduled job",
    )

    # Last Sync Timestamps
    last_order_sync = fields.Datetime(readonly=True)
    last_settlement_sync = fields.Datetime(readonly=True)
    last_question_sync = fields.Datetime(readonly=True)
    last_claim_sync = fields.Datetime(readonly=True)

    # Statistics
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

    def _marketplace_name(self):
        return _("Hepsiburada")

    def _marketplace_queue_channel(self):
        return "root.hepsiburada.order"

    def _marketplace_api_error_class(self):
        return HepsiburadaAPIError

    def _marketplace_cargo_provider_field(self):
        return "hepsiburada_cargo_provider_name"

    def _marketplace_count_models(self):
        return {
            "order_count": "hepsiburada.order",
            "settlement_count": "hepsiburada.settlement",
            "question_count": "hepsiburada.question",
            "claim_count": "hepsiburada.claim",
        }

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

    # ==================== Order Import ====================

    def action_import_orders(self):
        """Manually trigger order import."""
        self.ensure_one()
        return self._marketplace_queue_action(
            "_import_orders",
            _("Import Hepsiburada orders: %s") % self.name,
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

        The /orders and /orders/paymentawaiting endpoints return flat line items
        with nested shippingAddress/invoice objects.  This helper normalizes
        field names and groups them by orderNumber so the same _import_order()
        pipeline can process them.

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
        """Import orders from all Hepsiburada endpoints.

        Endpoints:
        - /orders (paketlenecek - flat line items, grouped by orderNumber)
        - /orders/paymentawaiting (ödemesi bekleniyor - flat line items)
        - /packages (paketlenmiş / gönderime hazır)
        - /packages/shipped (kargoda)
        - /packages/delivered (teslim edildi)
        - /packages/undelivered (teslim edilemedi)
        - /packages/cancelled (iptal edildi)
        """
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
                (client.get_cancelled_orders, "cancelled", "Cancelled"),
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

    # ==================== Settlement Import ====================

    def action_import_settlements(self):
        """Manually trigger settlement import."""
        self.ensure_one()
        return self._marketplace_queue_action(
            "_import_settlements",
            _("Import Hepsiburada settlements: %s") % self.name,
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
        return self._marketplace_action_view(_("Orders"), "hepsiburada.order")

    def action_view_settlements(self):
        """View settlements for this backend."""
        return self._marketplace_action_view(_("Settlements"), "hepsiburada.settlement")

    def action_view_questions(self):
        """View questions for this backend."""
        return self._marketplace_action_view(_("Questions"), "hepsiburada.question")

    def action_view_claims(self):
        """View claims for this backend."""
        return self._marketplace_action_view(_("Claims"), "hepsiburada.claim")

    # ==================== Claim Import ====================

    def action_import_claims(self):
        """Manually trigger claim import."""
        self.ensure_one()
        return self._marketplace_queue_action(
            "_import_claims",
            _("Import Hepsiburada claims: %s") % self.name,
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
        return self._marketplace_queue_action(
            "_import_questions",
            _("Import Hepsiburada questions: %s") % self.name,
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

    # ==================== Cron Methods ====================

    @api.model
    def _cron_import_orders(self):
        """Cron job to import orders from all active backends."""
        self._marketplace_cron_queue(
            "auto_import_orders",
            "_import_orders",
            _("Import Hepsiburada orders: %s"),
        )

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
        self._marketplace_cron_queue(
            "auto_import_settlements",
            "_import_settlements",
            _("Import Hepsiburada settlements: %s"),
        )

    @api.model
    def _cron_import_questions(self):
        """Cron job to import questions from all active backends."""
        self._marketplace_cron_queue(
            "auto_import_questions",
            "_import_questions",
            _("Import Hepsiburada questions: %s"),
        )

    @api.model
    def _cron_import_claims(self):
        """Cron job to import claims from all active backends."""
        self._marketplace_cron_queue(
            "auto_import_claims",
            "_import_claims",
            _("Import Hepsiburada claims: %s"),
        )

    def _send_pending_invoices(self):
        """Find Hepsiburada orders with pending invoices and queue sends."""
        return self._send_pending_marketplace_invoices(
            "hepsiburada.order",
            "hb_order_number",
            extra_domain=[("hb_status", "!=", "cancelled")],
        )

    # ==================== Missing Invoice Sync ====================

    def action_sync_missing_invoices(self):
        """Manually trigger missing invoice sync."""
        self.ensure_one()
        return self._marketplace_queue_action(
            "_sync_missing_invoices",
            _("Sync missing invoices: %s") % self.name,
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
