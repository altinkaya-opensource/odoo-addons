# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import json
import logging
import re
from datetime import datetime

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from .trendyol_backend import _trendyol_ts_to_utc, _utc_to_trendyol_ts
from .trendyol_request import TrendyolAPIError

_logger = logging.getLogger(__name__)

INDIVIDUAL_VAT = "11111111111"
PLACEHOLDER_VATS = frozenset({INDIVIDUAL_VAT, "2222222222"})


class TrendyolOrder(models.Model):
    _name = "trendyol.order"
    _description = "Trendyol Order"
    _inherit = ["marketplace.order.mixin"]
    _inherits = {"sale.order": "odoo_id"}
    _order = "create_date desc"

    odoo_id = fields.Many2one(
        "sale.order",
        string="Odoo Order",
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
    trendyol_order_number = fields.Char(
        required=True,
        index=True,
    )
    trendyol_package_id = fields.Char(
        string="Package ID",
        required=True,
        index=True,
        help="Shipment package ID in Trendyol",
    )
    trendyol_customer_id = fields.Char(
        string="Customer ID",
        index=True,
    )

    # Status
    trendyol_status = fields.Selection(
        [
            ("created", "Created"),
            ("awaiting", "Awaiting"),
            ("picking", "Picking"),
            ("invoiced", "Invoiced"),
            ("shipped", "Shipped"),
            ("cancelled", "Cancelled"),
            ("delivered", "Delivered"),
            ("undelivered", "Undelivered"),
            ("returned", "Returned"),
            ("unpacked", "Unpacked"),
            ("unsupplied", "Unsupplied"),
            ("at_collection_point", "At Collection Point"),
        ],
        default="created",
        required=True,
        index=True,
    )

    # Shipping info
    cargo_tracking_number = fields.Char(string="Tracking Number")
    cargo_tracking_link = fields.Char(string="Tracking Link")
    cargo_provider_name = fields.Char(string="Cargo Provider")
    cargo_provider_id = fields.Integer(string="Cargo Provider ID")

    # Invoice
    invoice_link_sent = fields.Boolean(
        default=False,
    )
    invoice_sent_date = fields.Datetime(
        readonly=True,
    )

    # Raw data
    raw_data = fields.Text(
        help="Original JSON data from Trendyol",
    )

    # Computed fields
    order_date = fields.Datetime(
        compute="_compute_order_date",
        store=True,
    )

    _sql_constraints = [
        (
            "package_id_backend_uniq",
            "unique(trendyol_package_id, backend_id)",
            "Package ID must be unique per backend!",
        ),
    ]

    def _marketplace_order_number(self):
        return self.trendyol_order_number

    def _marketplace_delivery_state_map(self):
        return {
            "picking": "shipping_recorded_in_carrier",
            "invoiced": "shipping_recorded_in_carrier",
            "shipped": "in_transit",
            "delivered": "customer_delivered",
            "cancelled": "canceled_shipment",
            "undelivered": "incident",
            "returned": "warehouse_delivered",
        }

    def _marketplace_shipped_statuses(self):
        return ("shipped",)

    def _marketplace_delivered_statuses(self):
        return ("delivered",)

    @api.depends("raw_data")
    def _compute_order_date(self):
        for order in self:
            if order.raw_data:
                try:
                    data = json.loads(order.raw_data)
                    order_date_ts = data.get("orderDate")
                    if order_date_ts:
                        order.order_date = _trendyol_ts_to_utc(order_date_ts)
                        continue
                except (json.JSONDecodeError, TypeError):
                    _logger.debug("Failed to parse order date from raw_data")
            order.order_date = order.create_date

    @api.model
    def _import_order(self, backend, order_data):
        """Import a single order from Trendyol API response.

        Args:
            backend: trendyol.backend record
            order_data: Dict from API response

        Returns:
            trendyol.order record
        """
        package_value = order_data.get("shipmentPackageId") or order_data.get("id")
        order_number_value = order_data.get("orderNumber")

        if not package_value or not order_number_value:
            _logger.warning("Invalid order data: missing package_id or order_number")
            return False

        package_id = str(package_value)
        order_number = str(order_number_value)

        # Check if already imported
        existing = self.search(
            [
                ("backend_id", "=", backend.id),
                ("trendyol_package_id", "=", package_id),
            ],
            limit=1,
        )

        if existing:
            existing._update_from_trendyol_data(order_data)
            return existing

        # Create new order
        try:
            main_partner, shipping_partner = self._get_or_create_partner(
                backend, order_data
            )
            order_vals = self._prepare_order_values(
                backend, order_data, main_partner, shipping_partner
            )
            sale_order = self.env["sale.order"].create(order_vals)

            # Create binding before lines so that trendyol_binding_ids
            # exists when _compute_price_unit and explode_set_contents
            # run on the new sale order lines.
            binding = self.create(
                {
                    "odoo_id": sale_order.id,
                    "backend_id": backend.id,
                    "trendyol_order_number": order_number,
                    "trendyol_package_id": package_id,
                    "trendyol_customer_id": str(order_data.get("customerId", "")),
                    "trendyol_status": self._map_status(order_data.get("status"))
                    or "created",
                    "cargo_provider_name": order_data.get("cargoProviderName"),
                    "cargo_provider_id": order_data.get("cargoProviderId"),
                    "cargo_tracking_number": order_data.get("cargoTrackingNumber"),
                    "cargo_tracking_link": order_data.get("cargoTrackingLink"),
                    "raw_data": json.dumps(order_data, indent=2, ensure_ascii=False),
                }
            )

            # Create order lines
            lines = order_data.get("lines", [])
            for line_data in lines:
                line_vals = self._prepare_line_values(backend, sale_order, line_data)
                if line_vals:
                    self.env["sale.order.line"].create(line_vals)

            # Auto-confirm if configured
            if backend.auto_confirm_orders:
                sale_order.ignore_exception = True
                sale_order.with_context(bypass_risk=True).action_confirm()

            _logger.info(
                "Imported order %s (package: %s)",
                order_number,
                package_id,
            )
            return binding

        except Exception as e:
            _logger.error(
                "Failed to import order %s: %s",
                order_number,
                str(e),
            )
            raise

    def _update_from_trendyol_data(self, order_data):
        """Refresh mutable package data on an existing binding."""
        self.ensure_one()
        vals = {
            "raw_data": json.dumps(order_data, indent=2, ensure_ascii=False),
        }
        field_map = {
            "cargoProviderName": "cargo_provider_name",
            "cargoProviderId": "cargo_provider_id",
            "cargoTrackingNumber": "cargo_tracking_number",
            "cargoTrackingLink": "cargo_tracking_link",
        }
        for api_field, odoo_field in field_map.items():
            # An empty payload value means "not shipped yet" for Trendyol, so
            # it must never clear tracking data we already stored.
            value = order_data.get(api_field)
            if value:
                vals[odoo_field] = value

        new_status = self._map_status(order_data.get("status"))
        if new_status:
            vals["trendyol_status"] = new_status

        old_status = self.trendyol_status
        self.write(vals)
        if new_status and new_status != old_status:
            self._update_picking_delivery_state(new_status)
            if new_status == "cancelled":
                self.odoo_id.action_trendyol_cancel()
        return self

    @api.model
    def _map_status(self, trendyol_status):
        """Map Trendyol status to our status field.

        Args:
            trendyol_status: Status string from API

        Returns:
            Status selection value
        """
        status_map = {
            "Created": "created",
            "Awaiting": "awaiting",
            "Picking": "picking",
            "Invoiced": "invoiced",
            "Shipped": "shipped",
            "Cancelled": "cancelled",
            "Delivered": "delivered",
            "UnDelivered": "undelivered",
            "Returned": "returned",
            "UnPacked": "unpacked",
            "UnSupplied": "unsupplied",
            "AtCollectionPoint": "at_collection_point",
        }
        return status_map.get(trendyol_status)

    @api.model
    def _partner_vat_digits(self, vat):
        """Return the digits-only form of a tax number."""
        return re.sub(r"\D+", "", vat or "")

    @api.model
    def _sanitize_partner_vat(self, vat):
        """Return a VAT that partner constraints accept, or False.

        Trendyol tax numbers are often mistyped. An invalid VAT must not
        abort the whole order import.
        """
        digits = self._partner_vat_digits(vat)
        if not digits:
            return False
        if digits in PLACEHOLDER_VATS:
            return digits
        Partner = self.env["res.partner"]
        candidates = [digits]
        if len(digits) == 11:
            candidates.extend((digits[:10], digits[1:]))
        elif len(digits) > 11:
            candidates.extend((digits[:11], digits[:10], digits[-11:], digits[-10:]))
        check_vat_tr = getattr(Partner, "check_vat_tr", None)
        seen = set()
        for candidate in candidates:
            if not candidate or candidate in seen:
                continue
            seen.add(candidate)
            if check_vat_tr:
                if check_vat_tr(candidate):
                    return candidate
                continue
            if len(candidate) in (10, 11):
                return candidate
        return False

    @api.model
    def _create_main_partner(self, Partner, partner_vals):
        """Create the invoice partner, dropping an invalid VAT if needed."""
        try:
            with self.env.cr.savepoint():
                return Partner.create(partner_vals)
        except (ValidationError, UserError) as exc:
            vat = partner_vals.get("vat")
            if not vat or vat in PLACEHOLDER_VATS:
                raise
            existing = Partner.search(
                [
                    ("vat", "=", vat),
                    ("parent_id", "=", False),
                ],
                limit=1,
            )
            if existing:
                _logger.warning(
                    "Reusing partner %s for Trendyol VAT %s after create error: %s",
                    existing.display_name,
                    vat,
                    exc,
                )
                return existing
            _logger.warning(
                "Invalid VAT %s for Trendyol partner %s: %s; creating without VAT",
                vat,
                partner_vals.get("name"),
                exc,
            )
            partner_vals = dict(partner_vals)
            partner_vals["vat"] = False
            return Partner.create(partner_vals)

    @api.model
    def _get_or_create_partner(self, backend, order_data):
        """Get or create partner(s) from order data.

        Args:
            backend: trendyol.backend record
            order_data: Dict from API response

        Returns:
            Tuple of (main_partner, shipping_partner) res.partner records
        """
        main_partner = self._get_or_create_main_partner(backend, order_data)
        shipping_partner = self._get_or_create_shipping_partner(
            backend, order_data, main_partner
        )
        return main_partner, shipping_partner

    @api.model
    def _get_or_create_main_partner(self, backend, order_data):
        """Get or create main partner (commercial entity) from invoice address.

        For commercial orders with VAT, matches by VAT first.
        For individual customers, matches by trendyol_customer_id.

        Args:
            backend: trendyol.backend record
            order_data: Dict from API response

        Returns:
            res.partner record
        """
        Partner = self.env["res.partner"]

        customer_id = str(order_data.get("customerId", ""))
        invoice_address = order_data.get("invoiceAddress", {})
        raw_tax = (invoice_address.get("taxNumber") or "").strip()
        vat = self._sanitize_partner_vat(raw_tax)
        is_commercial = bool(raw_tax) and (
            self._partner_vat_digits(raw_tax) not in PLACEHOLDER_VATS
        )

        # For commercial orders, try VAT matching first
        # Skip matching for dummy/individual VAT to avoid address mismatches
        if is_commercial and vat:
            partner = Partner.search(
                [
                    ("vat", "=", vat),
                    ("company_id", "in", [False, backend.company_id.id]),
                    ("parent_id", "=", False),
                ],
                limit=1,
            )
            if partner:
                # Update trendyol_customer_id if missing
                if customer_id and not partner.trendyol_customer_id:
                    partner.trendyol_customer_id = customer_id
                return partner

        # Try to find by Trendyol customer ID
        if customer_id:
            partner = Partner.search(
                [
                    ("trendyol_customer_id", "=", customer_id),
                    ("company_id", "in", [False, backend.company_id.id]),
                    ("parent_id", "=", False),
                ],
                limit=1,
            )
            if partner:
                return partner

        # Create new partner from invoice address
        partner_vals = self._prepare_partner_values(
            backend, order_data, invoice_address, is_main=True
        )
        partner_vals["trendyol_customer_id"] = customer_id

        if is_commercial:
            if vat:
                partner_vals["vat"] = vat
            partner_vals["company_type"] = "company"
            tax_office = invoice_address.get("taxOffice", "").strip()
            if tax_office:
                partner_vals["tax_office_name"] = tax_office
            # Use company name if available
            if invoice_address.get("company"):
                partner_vals["name"] = invoice_address["company"]
        else:
            partner_vals["vat"] = INDIVIDUAL_VAT

        return self._create_main_partner(Partner, partner_vals)

    @api.model
    def _get_or_create_shipping_partner(self, backend, order_data, main_partner):
        """Get or create shipping address as child partner if different from invoice.

        Args:
            backend: trendyol.backend record
            order_data: Dict from API response
            main_partner: res.partner record (main/invoice partner)

        Returns:
            res.partner record (shipping address, may be same as main_partner)
        """
        Partner = self.env["res.partner"]

        invoice_address = order_data.get("invoiceAddress", {})
        shipment_address = order_data.get("shipmentAddress", {})

        invoice_addr_id = str(invoice_address.get("id", ""))
        shipment_addr_id = str(shipment_address.get("id", ""))

        # If same address, use main partner
        if invoice_addr_id == shipment_addr_id:
            return main_partner

        # Try to find existing shipping address
        if shipment_addr_id:
            shipping_partner = Partner.search(
                [
                    ("trendyol_address_id", "=", shipment_addr_id),
                    ("parent_id", "=", main_partner.id),
                ],
                limit=1,
            )
            if shipping_partner:
                return shipping_partner

        # Create child partner for shipping address
        partner_vals = self._prepare_partner_values(
            backend, order_data, shipment_address, is_main=False
        )
        partner_vals["parent_id"] = main_partner.id
        partner_vals["type"] = "delivery"
        partner_vals["trendyol_address_id"] = shipment_addr_id

        return Partner.create(partner_vals)

    @api.model
    def _prepare_partner_values(self, backend, order_data, address, is_main=True):
        """Prepare partner values from address data.

        Args:
            backend: trendyol.backend record
            order_data: Dict from API response
            address: Address dict (invoiceAddress or shipmentAddress)
            is_main: Boolean, True for main partner, False for child address

        Returns:
            Dict of res.partner values
        """
        # Extract name
        first_name = address.get("firstName", "")
        last_name = address.get("lastName", "")
        full_name = address.get("fullName") or f"{first_name} {last_name}".strip()

        if not full_name:
            full_name = (
                order_data.get("customerFirstName", "")
                + " "
                + order_data.get("customerLastName", "")
            )
            full_name = full_name.strip() or _("Trendyol Customer")

        # Get or create country/state
        country = self._get_country(address)
        state = self._get_state(country, address)

        # Build address lines
        address1 = address.get("address1", "")
        address2 = address.get("address2", "")
        full_address = address.get("fullAddress", "")

        # Use fullAddress if address1 is empty
        if not address1 and full_address:
            address1 = full_address
            address2 = ""

        partner_vals = {
            "name": full_name,
            "street": address1,
            "street2": address2,
            "city": address.get("city", ""),
            "zip": address.get("postalCode", ""),
            "phone": address.get("phone", ""),
            "email": order_data.get("customerEmail", ""),
            "country_id": country.id if country else False,
            "state_id": state.id if state else False,
            "trendyol_address_id": str(address.get("id", "")),
            # Default to blacklisted to prevent accidental marketing emails
            "is_blacklisted": True,
        }

        if is_main:
            partner_vals["company_id"] = backend.company_id.id
            partner_vals["customer_rank"] = 1

        return partner_vals

    @api.model
    def _get_country(self, address):
        """Get country from address data.

        Args:
            address: Address dict from API

        Returns:
            res.country record or None
        """
        country_code = address.get("countryCode", "TR")
        return self._get_country_by_code(country_code)

    @api.model
    def _get_state(self, country, address):
        """Get state/province from address data.

        Args:
            country: res.country record
            address: Address dict from API

        Returns:
            res.country.state record or None
        """
        return self._get_state_by_name(country, address.get("city", ""))

    @api.model
    def _prepare_order_values(
        self, backend, order_data, main_partner, shipping_partner
    ):
        """Prepare sale.order values.

        Args:
            backend: trendyol.backend record
            order_data: Dict from API
            main_partner: res.partner record (invoice partner)
            shipping_partner: res.partner record (delivery address)

        Returns:
            Dict of sale.order values
        """
        # Parse order date (Trendyol timestamps are GMT+3)
        order_date = _trendyol_ts_to_utc(order_data.get("orderDate"))
        if not order_date:
            order_date = fields.Datetime.now()

        return self._prepare_marketplace_order_values(
            backend,
            main_partner,
            shipping_partner,
            order_date,
            str(order_data.get("orderNumber", "")),
            cargo_provider_name=order_data.get("cargoProviderName"),
        )

    @api.model
    def _prepare_line_values(self, backend, sale_order, line_data):
        """Prepare sale.order.line values.

        Args:
            backend: trendyol.backend record
            sale_order: sale.order record
            line_data: Line dict from API

        Returns:
            Dict of sale.order.line values
        """
        barcode = line_data.get("barcode")
        merchant_sku = line_data.get("merchantSku") or line_data.get("stockCode")
        quantity = line_data.get("quantity", 1)
        price_incl = line_data.get("price") or line_data.get("lineUnitPrice") or 0
        product_name = line_data.get("productName", "")
        vat_rate = line_data.get("vatRate", 0)

        # Find product by stock code (default_code) or barcode
        Product = self.env["product.product"]
        product = None

        if merchant_sku:
            product = Product.search([("default_code", "=", merchant_sku)], limit=1)
        if not product and barcode:
            product = Product.search([("barcode", "=", barcode)], limit=1)

        # Build line description
        sku_info = merchant_sku or barcode or _("N/A")
        if product:
            line_name = product_name or product.display_name
        else:
            # No product found - use fallback product or create note line
            line_name = product_name or _("Unknown Product")
            line_name = f"[{sku_info}] {line_name}"

            if backend.default_product_id:
                product = backend.default_product_id
                _logger.info(
                    "Product not mapped for barcode %s / SKU %s in order %s - "
                    "using fallback product %s",
                    barcode,
                    merchant_sku,
                    sale_order.name,
                    product.display_name,
                )
            else:
                # Create a note line (not invoiceable)
                _logger.warning(
                    "Product not mapped for barcode %s / SKU %s in order %s - "
                    "creating note line (no fallback product configured)",
                    barcode,
                    merchant_sku,
                    sale_order.name,
                )
                return self._prepare_unmapped_line_values(
                    sale_order,
                    line_name,
                    quantity,
                    price_incl,
                )

        # Trendyol prices are VAT-included.
        # `amount` is the original (undiscounted) unit price,
        # `price` is the unit price after discount.
        # We use `amount` as price_unit and compute the Odoo discount
        # percentage from the total discount to avoid double-discounting.
        discount_details = line_data.get("discountDetails") or []
        if discount_details:
            gross_total = sum(item.get("lineItemPrice", 0) for item in discount_details)
            discount_amount = sum(
                item.get("lineItemSellerDiscount", 0)
                + item.get("lineItemTyDiscount", 0)
                for item in discount_details
            )
            gross_unit_price = gross_total / quantity if quantity else 0
        else:
            gross_unit_price = line_data.get("amount") or price_incl
            discount_amount = line_data.get(
                "discount", line_data.get("lineSellerDiscount", 0)
            ) + line_data.get("tyDiscount", line_data.get("lineTyDiscount", 0))
            gross_total = (
                line_data.get("lineGrossAmount") or gross_unit_price * quantity
            )

        price_unit = gross_unit_price
        discount_pct = 0.0
        if discount_amount and gross_total:
            discount_pct = (discount_amount / gross_total) * 100

        vals = {
            "order_id": sale_order.id,
            "name": line_name,
            "product_id": product.id,
            "product_uom_qty": quantity,
            "price_unit": price_unit,
            "discount": discount_pct,
        }

        # Find and apply matching tax
        tax = self._get_tax_for_rate(backend, vat_rate)
        if tax:
            vals["tax_id"] = [(6, 0, [tax.id])]

        return vals

    @api.model
    def _get_tax_for_rate(self, backend, vat_rate):
        """Find sale tax matching the given VAT rate.

        Args:
            backend: trendyol.backend record
            vat_rate: VAT rate percentage (e.g., 10, 18, 20)

        Returns:
            account.tax record or None
        """
        return super()._get_tax_for_rate(backend, vat_rate)

    def action_update_tracking(self):
        """Update tracking number in Trendyol."""
        self.ensure_one()

        if not self.cargo_tracking_number:
            raise UserError(_("No tracking number to send."))

        self.with_delay(
            channel="root.trendyol.order",
            description=_("Update tracking: %s") % self.trendyol_order_number,
        )._update_tracking()

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Update Queued"),
                "message": _("Tracking number update has been queued."),
                "type": "info",
                "sticky": False,
            },
        }

    def _update_tracking(self):
        """Send tracking number to Trendyol API."""
        self.ensure_one()
        client = self.backend_id._get_api_client()

        try:
            client.update_tracking_number(
                int(self.trendyol_package_id),
                self.cargo_tracking_number,
                self.cargo_provider_id,
            )
            self.trendyol_status = "shipped"
            _logger.info(
                "Updated tracking for order %s: %s",
                self.trendyol_order_number,
                self.cargo_tracking_number,
            )
        except TrendyolAPIError as e:
            _logger.error(
                "Failed to update tracking for %s: %s",
                self.trendyol_order_number,
                str(e),
            )
            raise

    def action_send_invoice(self):
        """Send invoice link to Trendyol."""
        self.ensure_one()

        if self.invoice_link_sent:
            raise UserError(_("Invoice link already sent."))

        if not self.odoo_id.invoice_ids.filtered(lambda i: i.state == "posted"):
            raise UserError(_("No posted invoice found for this order."))

        self.with_delay(
            channel="root.trendyol.order",
            description=_("Send invoice: %s") % self.trendyol_order_number,
        )._send_invoice()

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Send Queued"),
                "message": _("Invoice link send has been queued."),
                "type": "info",
                "sticky": False,
            },
        }

    def _send_invoice(self):
        """Send Invoiced status and invoice link to Trendyol API."""
        self.ensure_one()
        client = self.backend_id._get_api_client()

        # Get posted invoice
        invoice = self.odoo_id.invoice_ids.filtered(
            lambda i: i.state == "posted" and i.move_type == "out_invoice"
        )[:1]

        if not invoice:
            _logger.warning(
                "No posted invoice found for order %s, skipping.",
                self.trendyol_order_number,
            )
            return

        # Step 1: Send "Invoiced" status via updatePackage (if in picking state)
        if self.trendyol_status == "picking":
            lines = self._get_trendyol_lines()
            if lines:
                try:
                    client.update_package_status(
                        int(self.trendyol_package_id),
                        status="Invoiced",
                        lines=lines,
                        params={"invoiceNumber": invoice.name},
                    )
                except TrendyolAPIError as e:
                    _logger.error(
                        "Failed to send Invoiced status for %s: %s",
                        self.trendyol_order_number,
                        str(e),
                    )
                    raise

        # Step 2: Send invoice link (uses e-invoice PDF URL if available)
        base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url")
        invoice_url = f"{base_url}{invoice.get_portal_url()}"

        # Trendyol expects invoiceDateTime as Unix timestamp in milliseconds
        invoice_ts = None
        if invoice.invoice_date:
            invoice_dt = datetime.combine(invoice.invoice_date, datetime.min.time())
            invoice_ts = _utc_to_trendyol_ts(invoice_dt)

        try:
            client.send_invoice_link(
                int(self.trendyol_package_id),
                invoice_url,
                invoice.name,
                invoice_ts,
            )
        except TrendyolAPIError as e:
            if e.status_code == 409:
                # Invoice link already exists (e.g. manually uploaded)
                _logger.info(
                    "Invoice link already exists for order %s, "
                    "marking as sent locally.",
                    self.trendyol_order_number,
                )
            else:
                _logger.error(
                    "Failed to send invoice for %s: %s",
                    self.trendyol_order_number,
                    str(e),
                )
                raise

        self.invoice_link_sent = True
        self.invoice_sent_date = fields.Datetime.now()
        if self.trendyol_status not in ("shipped", "delivered"):
            self.trendyol_status = "invoiced"
        _logger.info(
            "Invoice link processed for order %s: %s",
            self.trendyol_order_number,
            invoice.name,
        )

    def action_cancel_in_trendyol(self):
        """Cancel order in Trendyol."""
        self.ensure_one()

        if self.trendyol_status in ("shipped", "delivered"):
            raise UserError(_("Cannot cancel shipped or delivered orders."))

        self.with_delay(
            channel="root.trendyol.order",
            description=_("Cancel order: %s") % self.trendyol_order_number,
        )._cancel_in_trendyol()

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Cancel Queued"),
                "message": _("Order cancellation has been queued."),
                "type": "info",
                "sticky": False,
            },
        }

    def _get_trendyol_lines(self):
        """Get Trendyol line items from raw data for API calls.

        Returns:
            List of dicts with 'lineId' and 'quantity'
        """
        self.ensure_one()
        try:
            data = json.loads(self.raw_data or "{}")
            lines = data.get("lines", [])
        except (json.JSONDecodeError, TypeError):
            return []
        return [
            {
                "lineId": line.get("lineId") or line.get("id"),
                "quantity": line.get("quantity"),
            }
            for line in lines
            if line.get("lineId") or line.get("id")
        ]

    def _update_picking_delivery_state(self, trendyol_status):
        """Update stock.picking delivery_state from Trendyol status.

        Maps Trendyol status to OCA delivery_state values and writes
        to related outgoing pickings.

        Args:
            trendyol_status: Mapped status string (e.g., 'shipped', 'delivered')
        """
        return super()._update_picking_delivery_state(trendyol_status)

    def action_check_status(self):
        """Check current order status from Trendyol API."""
        self.ensure_one()
        self._check_order_status()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Status Updated"),
                "message": _("Trendyol status: %s") % self.trendyol_status,
                "type": "info",
                "sticky": False,
            },
        }

    def _check_order_status(self):
        """Fetch current order status from Trendyol API and update locally.

        If the order is cancelled/unsupplied on Trendyol, updates the
        local trendyol_status, picking delivery state, and cancels the
        Odoo sale order.

        Returns:
            The updated trendyol_status string
        """
        self.ensure_one()
        client = self.backend_id._get_api_client()
        result = client.get_orders(
            order_number=self.trendyol_order_number,
        )

        packages = result.get("content", [])
        for package in packages:
            if str(package.get("id")) != self.trendyol_package_id:
                continue
            new_status = self._map_status(package.get("status"))
            if not new_status:
                break
            if self.trendyol_status != new_status:
                self.trendyol_status = new_status
                self._update_picking_delivery_state(new_status)
                if new_status in ("cancelled", "unsupplied"):
                    self.odoo_id.action_trendyol_cancel()
            break

        return self.trendyol_status

    def _notify_picking_status(self):
        """Notify Trendyol that the package is being prepared (Picking status)."""
        self.ensure_one()
        client = self.backend_id._get_api_client()
        lines = self._get_trendyol_lines()
        if not lines:
            _logger.warning(
                "No lines found for picking notification: %s",
                self.trendyol_order_number,
            )
            return
        try:
            client.update_package_status(
                int(self.trendyol_package_id),
                status="Picking",
                lines=lines,
            )
            self.trendyol_status = "picking"
            _logger.info(
                "Notified Trendyol picking status for order %s",
                self.trendyol_order_number,
            )
        except TrendyolAPIError as e:
            _logger.error(
                "Failed to notify picking for %s: %s",
                self.trendyol_order_number,
                str(e),
            )
            raise

    def _cancel_in_trendyol(self, reason_id=None):
        """Cancel order in Trendyol API."""
        self.ensure_one()
        client = self.backend_id._get_api_client()

        cancel_lines = self._get_trendyol_lines()

        if not cancel_lines:
            raise UserError(_("No order lines found to cancel."))

        try:
            client.cancel_order_items(
                int(self.trendyol_package_id),
                cancel_lines,
                reason_id=reason_id,
            )
            self.trendyol_status = "cancelled"
            self.odoo_id.action_trendyol_cancel()
            _logger.info("Cancelled order %s", self.trendyol_order_number)
        except TrendyolAPIError as e:
            _logger.error(
                "Failed to cancel order %s: %s",
                self.trendyol_order_number,
                str(e),
            )
            raise

    def action_view_in_trendyol(self):
        """Open order in Trendyol seller panel."""
        self.ensure_one()
        base_url = "https://partner.trendyol.com"
        url = f"{base_url}/orders/shipment-packages/{self.trendyol_package_id}"
        return {
            "type": "ir.actions.act_url",
            "url": url,
            "target": "new",
        }
