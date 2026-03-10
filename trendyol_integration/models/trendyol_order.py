# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import json
import logging
from datetime import datetime

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .trendyol_backend import _trendyol_ts_to_utc, _utc_to_trendyol_ts
from .trendyol_request import TrendyolAPIError

_logger = logging.getLogger(__name__)

INDIVIDUAL_VAT = "11111111111"


class TrendyolOrder(models.Model):
    _name = "trendyol.order"
    _description = "Trendyol Order"
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
        package_id = str(order_data.get("id") or order_data.get("shipmentPackageId"))
        order_number = str(order_data.get("orderNumber"))

        if not package_id or not order_number:
            _logger.warning("Invalid order data: missing package_id or order_number")
            return False

        # Check if already imported
        existing = self.search(
            [
                ("backend_id", "=", backend.id),
                ("trendyol_package_id", "=", package_id),
            ],
            limit=1,
        )

        if existing:
            # Update status if changed
            new_status = self._map_status(order_data.get("status"))
            if existing.trendyol_status != new_status:
                existing.trendyol_status = new_status
                existing.raw_data = json.dumps(order_data, indent=2, ensure_ascii=False)
                existing._update_picking_delivery_state(new_status)
                # Cancel the Odoo sale order if Trendyol status is cancelled
                if new_status == "cancelled" and existing.odoo_id.state not in (
                    "done",
                    "cancel",
                ):
                    existing.odoo_id.with_context(
                        from_trendyol_cancel=True,
                        disable_cancel_warning=True,
                    ).action_cancel()
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
                    "trendyol_status": self._map_status(order_data.get("status")),
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
        return status_map.get(trendyol_status, "created")

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
        is_commercial = bool(invoice_address.get("taxNumber"))

        # For commercial orders, try VAT matching first
        # Skip matching for dummy/individual VAT to avoid address mismatches
        if is_commercial:
            vat = invoice_address.get("taxNumber", "").strip()
            if vat and vat != INDIVIDUAL_VAT:
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
            partner_vals["vat"] = invoice_address.get("taxNumber", "").strip()
            partner_vals["company_type"] = "company"
            tax_office = invoice_address.get("taxOffice", "").strip()
            if tax_office:
                partner_vals["tax_office_name"] = tax_office
            # Use company name if available
            if invoice_address.get("company"):
                partner_vals["name"] = invoice_address["company"]
        else:
            partner_vals["vat"] = INDIVIDUAL_VAT

        return Partner.create(partner_vals)

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
        Country = self.env["res.country"]

        # Trendyol is Turkey-only for now
        country_code = address.get("countryCode", "TR")
        return Country.search([("code", "=", country_code)], limit=1)

    @api.model
    def _get_state(self, country, address):
        """Get state/province from address data.

        Args:
            country: res.country record
            address: Address dict from API

        Returns:
            res.country.state record or None
        """
        if not country:
            return None

        State = self.env["res.country.state"]

        # Try city name as state (Turkish provinces)
        city = address.get("city", "")
        if city:
            state = State.search(
                [
                    ("country_id", "=", country.id),
                    "|",
                    ("name", "=ilike", city),
                    ("code", "=ilike", city),
                ],
                limit=1,
            )
            if state:
                return state

        return None

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

        vals = {
            "partner_id": main_partner.id,
            "partner_invoice_id": main_partner.id,
            "partner_shipping_id": shipping_partner.id,
            "date_order": order_date,
            "company_id": backend.company_id.id,
            "warehouse_id": backend.warehouse_ids[:1].id,
            "pricelist_id": backend.pricelist_id.id,
            "client_order_ref": str(order_data.get("orderNumber", "")),
        }

        if backend.sales_team_id:
            vals["team_id"] = backend.sales_team_id.id
        if backend.fiscal_position_id:
            vals["fiscal_position_id"] = backend.fiscal_position_id.id
        if backend.source_id:
            vals["source_id"] = backend.source_id.id
        carrier = backend._get_carrier_for_cargo_provider(
            order_data.get("cargoProviderName")
        )
        if carrier:
            vals["carrier_id"] = carrier.id

        return vals

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
        merchant_sku = line_data.get("merchantSku")
        quantity = line_data.get("quantity", 1)
        price_incl = line_data.get("price", 0)
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
                return {
                    "order_id": sale_order.id,
                    "display_type": "line_note",
                    "name": _(
                        "UNMAPPED: %(product)s (Qty: %(qty)s, Price: %(price)s)",
                        product=line_name,
                        qty=quantity,
                        price=price_incl,
                    ),
                }

        # Trendyol prices are VAT-included; use as-is with
        # price_include taxes (Odoo checkpoint mechanism prevents drift)
        price_unit = price_incl

        # Trendyol sends discount as absolute amount (TRY), Odoo expects percentage
        discount_amount = line_data.get("discount", 0)
        discount_pct = 0.0
        if discount_amount and price_incl and quantity:
            discount_pct = (discount_amount / (price_incl * quantity)) * 100

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
        if not vat_rate:
            return None

        Tax = self.env["account.tax"]
        # Search for price-included tax with matching rate
        tax = Tax.search(
            [
                ("type_tax_use", "=", "sale"),
                ("amount", "=", vat_rate),
                ("price_include", "=", True),
                ("company_id", "=", backend.company_id.id),
            ],
            limit=1,
        )
        return tax

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
            {"lineId": line.get("id"), "quantity": line.get("quantity")}
            for line in lines
            if line.get("id")
        ]

    def _update_picking_delivery_state(self, trendyol_status):
        """Update stock.picking delivery_state from Trendyol status.

        Maps Trendyol status to OCA delivery_state values and writes
        to related outgoing pickings.

        Args:
            trendyol_status: Mapped status string (e.g., 'shipped', 'delivered')
        """
        self.ensure_one()
        state_map = {
            "picking": "shipping_recorded_in_carrier",
            "invoiced": "shipping_recorded_in_carrier",
            "shipped": "in_transit",
            "delivered": "customer_delivered",
            "cancelled": "canceled_shipment",
            "undelivered": "incident",
            "returned": "warehouse_delivered",
        }
        delivery_state = state_map.get(trendyol_status)
        if not delivery_state:
            return
        pickings = self.odoo_id.picking_ids.filtered(
            lambda p: p.picking_type_code == "outgoing"
        )
        for picking in pickings:
            vals = {"delivery_state": delivery_state}
            if trendyol_status == "shipped":
                vals["date_shipped"] = fields.Date.today()
            if trendyol_status == "delivered":
                vals["date_delivered"] = fields.Datetime.now()
            picking.write(vals)

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
            # Also cancel in Odoo, bypassing the Trendyol guard
            # and sale_cancel_reason wizard
            if self.odoo_id.state not in ("done", "cancel"):
                self.odoo_id.with_context(
                    from_trendyol_cancel=True,
                    disable_cancel_warning=True,
                ).action_cancel()
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
