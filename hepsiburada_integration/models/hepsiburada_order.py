# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import json
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from odoo.addons.marketplace_integration_base.models.marketplace_order import (
    INDIVIDUAL_VAT,
)

from .hepsiburada_backend import _parse_hb_datetime
from .hepsiburada_request import HepsiburadaAPIError

_logger = logging.getLogger(__name__)


class HepsiburadaOrder(models.Model):
    _name = "hepsiburada.order"
    _description = "Hepsiburada Order"
    _inherit = ["marketplace.order"]
    _order = "create_date desc"

    backend_id = fields.Many2one(
        "hepsiburada.backend",
        required=True,
        ondelete="cascade",
        index=True,
    )

    # Hepsiburada identifiers
    hb_order_number = fields.Char(
        string="Order Number",
        required=True,
        index=True,
    )
    hb_order_id = fields.Char(
        string="Order ID",
        index=True,
        help="Hepsiburada orderId GUID",
    )
    hb_customer_id = fields.Char(
        string="Customer ID",
        index=True,
    )
    hb_customer_name = fields.Char(
        string="Customer Name",
    )
    hb_full_address = fields.Char(
        string="Full Address",
        help="Concatenated address for easy searching",
    )

    # Status
    hb_status = fields.Selection(
        [
            ("open", "Paketlenecek"),
            ("packaged", "Paketlendi"),
            ("in_transit", "Kargoda"),
            ("delivered", "Teslim Edildi"),
            ("undelivered", "Teslim Edilemedi"),
            ("payment_awaiting", "Ödeme Bekliyor"),
            ("cancelled", "İptal Edildi"),
        ],
        default="open",
        required=True,
        index=True,
    )

    # Package info
    hb_package_number = fields.Char(string="Package Number")
    hb_cargo_barcode = fields.Char(string="Cargo Barcode")

    # Delivery info
    delivery_type = fields.Char(help="StandardDelivery / BT / YT")
    due_date = fields.Datetime(help="Last date to ship")
    is_overdue = fields.Boolean(
        compute="_compute_is_overdue",
        search="_search_is_overdue",
    )

    # Line item tracking for idempotency
    hb_line_item_ids = fields.One2many(
        "hepsiburada.order.line",
        "hb_order_id",
        string="HB Line Items",
    )

    # Invoice tracking
    hb_missing_invoice = fields.Boolean(
        default=False,
        help="Hepsiburada reports this package as missing invoice",
    )

    _sql_constraints = [
        (
            "order_number_backend_uniq",
            "unique(hb_order_number, backend_id)",
            "Order number must be unique per backend!",
        ),
    ]

    @api.depends("due_date")
    def _compute_is_overdue(self):
        now = fields.Datetime.now()
        for rec in self:
            rec.is_overdue = bool(rec.due_date and rec.due_date < now)

    def _search_is_overdue(self, operator, value):
        if (operator == "=" and value) or (operator == "!=" and not value):
            return [("due_date", "<", fields.Datetime.now())]
        return [
            "|",
            ("due_date", "=", False),
            ("due_date", ">=", fields.Datetime.now()),
        ]

    # ── Delivery State Map Hook ──────────────────────────────────────────

    def _get_delivery_state_map(self):
        return {
            "packaged": "shipping_recorded_in_carrier",
            "in_transit": "in_transit",
            "delivered": "customer_delivered",
            "cancelled": "canceled_shipment",
            "undelivered": "incident",
        }

    # ── Order Import ─────────────────────────────────────────────────────

    @api.model
    def _import_order(self, backend, package_data):
        """Import an order from a package dict returned by the packages API.

        Args:
            backend: hepsiburada.backend record
            package_data: Package dict from HB packages API with nested items[]

        Returns:
            hepsiburada.order record (created or existing)
        """
        if not package_data:
            return False

        line_items = package_data.get("items", [])
        if not line_items:
            _logger.warning("HB package has no items, skipping")
            return False

        first_item = line_items[0]
        order_number = str(first_item.get("orderNumber", ""))

        if not order_number:
            _logger.warning("HB package items missing orderNumber, skipping")
            return False

        # Check if already imported
        existing = self.search(
            [
                ("backend_id", "=", backend.id),
                ("hb_order_number", "=", order_number),
            ],
            limit=1,
        )

        if existing:
            # Update status - use _hb_status tag set by endpoint
            new_status = package_data.get(
                "_hb_status",
                self._map_status(package_data.get("status")),
            )
            if existing.hb_status != new_status:
                existing.hb_status = new_status
                existing.raw_data = json.dumps(
                    package_data, indent=2, ensure_ascii=False
                )
                existing._update_picking_delivery_state(new_status)
                # Cancel the Odoo sale order if HB status is cancelled
                if new_status == "cancelled" and existing.odoo_id.state not in (
                    "done",
                    "cancel",
                ):
                    existing.odoo_id.with_context(
                        from_hepsiburada_cancel=True,
                        disable_cancel_warning=True,
                    ).action_cancel()

            # Update package number if it was empty and now available
            pkg_number = package_data.get("packageNumber", "")
            if pkg_number and not existing.hb_package_number:
                existing.hb_package_number = str(pkg_number)

            # Fetch tracking info for shipped/delivered packages
            if (
                existing.hb_package_number
                and not existing.cargo_tracking_number
                and new_status in ("packaged", "in_transit", "delivered", "undelivered")
            ):
                existing._fetch_tracking_from_api()

            # Add only NEW line items (idempotency)
            existing_line_ids = set(existing.hb_line_item_ids.mapped("hb_line_item_id"))
            new_items = [
                item
                for item in line_items
                if str(item.get("lineItemId", "")) not in existing_line_ids
            ]
            if new_items:
                for item in new_items:
                    self._add_line_to_order(backend, existing, item)
                _logger.info(
                    "Added %d new line items to existing HB order %s",
                    len(new_items),
                    order_number,
                )
            return existing

        # Create new order
        try:
            main_partner, shipping_partner = self._get_or_create_partner(
                backend, package_data
            )
            order_vals = self._prepare_order_values(
                backend, package_data, main_partner, shipping_partner
            )
            sale_order = self.env["sale.order"].create(order_vals)

            # Build full address for searching
            addr_parts = [
                package_data.get("shippingAddressDetail", ""),
                package_data.get("shippingDistrict", ""),
                package_data.get("shippingTown", ""),
                package_data.get("shippingCity", ""),
            ]
            full_address = " ".join(p.strip() for p in addr_parts if p and p.strip())

            # Create binding before lines
            binding = self.create(
                {
                    "odoo_id": sale_order.id,
                    "backend_id": backend.id,
                    "hb_order_number": order_number,
                    "hb_order_id": str(package_data.get("id", "")),
                    "hb_customer_id": str(package_data.get("customerId", "")),
                    "hb_status": package_data.get(
                        "_hb_status",
                        self._map_status(package_data.get("status")),
                    ),
                    "cargo_provider_name": package_data.get("cargoCompany", ""),
                    "hb_customer_name": package_data.get("customerName", ""),
                    "hb_full_address": full_address,
                    "hb_package_number": str(package_data.get("packageNumber", ""))
                    or False,
                    "hb_cargo_barcode": package_data.get("barcode", "") or False,
                    "delivery_type": first_item.get("deliveryType", ""),
                    "due_date": _parse_hb_datetime(package_data.get("dueDate")),
                    "raw_data": json.dumps(package_data, indent=2, ensure_ascii=False),
                }
            )

            # Create order lines from all HB line items
            for item in line_items:
                self._add_line_to_order(backend, binding, item)

            # Auto-confirm if configured
            if backend.auto_confirm_orders:
                sale_order.ignore_exception = True
                sale_order.with_context(bypass_risk=True).action_confirm()

            _logger.info(
                "Imported HB order %s with %d line items",
                order_number,
                len(line_items),
            )
            return binding

        except Exception:
            _logger.error(
                "Failed to import HB order %s",
                order_number,
                exc_info=True,
            )
            raise

    def _add_line_to_order(self, backend, binding, item):
        """Add a single HB line item to the order.

        Creates both the sale.order.line and the
        hepsiburada.order.line tracking record.
        """
        line_item_id = str(item.get("lineItemId", ""))
        if not line_item_id:
            _logger.warning("HB line item missing lineItemId, skipping")
            return

        line_vals = self._prepare_line_values(backend, binding.odoo_id, item)
        if not line_vals:
            return
        sale_line = self.env["sale.order.line"].create(line_vals)

        # Price fields from packages API structure
        price_data = item.get("price", {})
        total_price_data = item.get("totalPrice", {})
        commission_data = item.get("commission", {})

        self.env["hepsiburada.order.line"].create(
            {
                "hb_order_id": binding.id,
                "hb_line_item_id": line_item_id,
                "hb_sku": item.get("hbSku", ""),
                "merchant_sku": item.get("merchantSku", ""),
                "sale_line_id": sale_line.id,
                "quantity": item.get("quantity", 1),
                "unit_price": price_data.get("amount", 0)
                if isinstance(price_data, dict)
                else price_data or 0,
                "total_price": total_price_data.get("amount", 0)
                if isinstance(total_price_data, dict)
                else total_price_data or 0,
                "vat_amount": item.get("vat", 0),
                "vat_rate": item.get("vat", 0),
                "commission_amount": commission_data.get("amount", 0)
                if isinstance(commission_data, dict)
                else commission_data or 0,
                "status": binding.hb_status,
            }
        )

    # ── Status Mapping ───────────────────────────────────────────────────

    @api.model
    def _map_status(self, hb_status):
        """Map Hepsiburada status string to our status field."""
        status_map = {
            "Open": "open",
            "Unpacked": "open",
            "Packaged": "packaged",
            "InTransit": "in_transit",
            "Delivered": "delivered",
            "CancelledByMerchant": "cancelled",
            "CancelledByCustomer": "cancelled",
            "CancelledBySap": "cancelled",
            "ClaimCreated": "undelivered",
            "PaymentAwaiting": "payment_awaiting",
        }
        return status_map.get(hb_status, "open")

    # ── Partner Resolution ───────────────────────────────────────────────

    @api.model
    def _get_or_create_partner(self, backend, package_data):
        """Get or create partner(s) from HB package data.

        Package-level fields used:
            taxNumber, identityNo, taxOffice, customerName, customerId,
            companyName, billingAddress/City/District/Town/PostalCode/CountryCode,
            shippingAddressDetail/City/District/Town/CountryCode, recipientName,
            email, phoneNumber

        Returns:
            Tuple of (main_partner, shipping_partner)
        """
        main_partner = self._get_or_create_main_partner(backend, package_data)
        shipping_partner = self._get_or_create_shipping_partner(
            backend, package_data, main_partner
        )
        return main_partner, shipping_partner

    @api.model
    def _get_or_create_main_partner(self, backend, pkg):
        """Get or create main partner from HB package billing data."""
        Partner = self.env["res.partner"]

        tax_number = (pkg.get("taxNumber") or "").strip()
        tckn = (pkg.get("identityNo") or "").strip()
        is_commercial = bool(tax_number) and tax_number != INDIVIDUAL_VAT

        # 1. Match by VKN (tax number) for commercial orders
        if is_commercial:
            partner = Partner.search(
                [("vat", "=", tax_number), ("parent_id", "=", False)],
                limit=1,
            )
            if partner:
                return partner

        # 2. Match by TCKN for individual orders
        if tckn and tckn != INDIVIDUAL_VAT:
            partner = Partner.search(
                [("vat", "=", tckn), ("parent_id", "=", False)],
                limit=1,
            )
            if partner:
                return partner

        # 3. Match by hb_customer_id
        customer_id = str(pkg.get("customerId", ""))
        if customer_id:
            partner = Partner.search(
                [
                    ("hb_customer_id", "=", customer_id),
                    ("parent_id", "=", False),
                ],
                limit=1,
            )
            if partner:
                return partner

        # 4. Create new partner from billing data
        # For commercial orders use companyName, for individuals use customerName.
        # HB sends its own company name (e.g. "Hepsiburada Office") as
        # companyName for individual orders, which is not the real customer.
        if is_commercial:
            full_name = (pkg.get("companyName") or "").strip()
        else:
            full_name = ""
        if not full_name:
            full_name = (pkg.get("customerName") or "").strip()
        if not full_name:
            full_name = _("Hepsiburada Customer")

        billing_city = (pkg.get("billingCity") or "").strip()
        country = self._get_country(pkg.get("billingCountryCode", "TR"))
        state = self._get_state(country, billing_city)

        billing_district = (pkg.get("billingDistrict") or "").strip()
        billing_town = (pkg.get("billingTown") or "").strip()
        street2 = ""
        if billing_district and billing_town:
            street2 = f"{billing_district} / {billing_town}"
        elif billing_district:
            street2 = billing_district
        elif billing_town:
            street2 = billing_town

        partner_vals = {
            "name": full_name,
            "street": (pkg.get("billingAddress") or "").strip(),
            "street2": street2,
            "city": billing_city,
            "zip": (pkg.get("billingPostalCode") or "").strip(),
            "phone": pkg.get("phoneNumber", ""),
            "email": pkg.get("email", ""),
            "country_id": country.id if country else False,
            "state_id": state.id if state else False,
            "is_blacklisted": True,
            "customer_rank": 1,
            "hb_customer_id": customer_id,
        }

        if is_commercial:
            partner_vals["vat"] = tax_number
            partner_vals["company_type"] = "company"
            tax_office = (pkg.get("taxOffice") or "").strip()
            if tax_office:
                partner_vals["tax_office_name"] = tax_office
        elif tckn and tckn != INDIVIDUAL_VAT:
            partner_vals["vat"] = tckn
        else:
            partner_vals["vat"] = INDIVIDUAL_VAT

        return Partner.create(partner_vals)

    @api.model
    def _get_or_create_shipping_partner(self, backend, pkg, main_partner):
        """Get or create shipping address as child partner."""
        Partner = self.env["res.partner"]

        # Try to find existing shipping address by customer_id + parent
        customer_id = str(pkg.get("customerId", ""))
        if customer_id:
            shipping_partner = Partner.search(
                [
                    ("hb_address_id", "=", customer_id),
                    ("parent_id", "=", main_partner.id),
                    ("type", "=", "delivery"),
                ],
                limit=1,
            )
            if shipping_partner:
                return shipping_partner

        # Create child partner for shipping address
        recipient_name = (pkg.get("recipientName") or "").strip()
        if not recipient_name:
            recipient_name = (pkg.get("customerName") or "").strip()
        if not recipient_name:
            recipient_name = main_partner.name

        shipping_city = (pkg.get("shippingCity") or "").strip()
        country = self._get_country(pkg.get("shippingCountryCode", "TR"))
        state = self._get_state(country, shipping_city)

        shipping_district = (pkg.get("shippingDistrict") or "").strip()
        shipping_town = (pkg.get("shippingTown") or "").strip()
        street2 = ""
        if shipping_district and shipping_town:
            street2 = f"{shipping_district} / {shipping_town}"
        elif shipping_district:
            street2 = shipping_district
        elif shipping_town:
            street2 = shipping_town

        partner_vals = {
            "parent_id": main_partner.id,
            "type": "delivery",
            "name": recipient_name,
            "street": (pkg.get("shippingAddressDetail") or "").strip(),
            "street2": street2,
            "city": shipping_city,
            "phone": pkg.get("phoneNumber", ""),
            "email": pkg.get("email", ""),
            "country_id": country.id if country else False,
            "state_id": state.id if state else False,
            "is_blacklisted": True,
            "hb_address_id": customer_id,
        }

        return Partner.create(partner_vals)

    # ── Order Values ─────────────────────────────────────────────────────

    @api.model
    def _prepare_order_values(
        self, backend, package_data, main_partner, shipping_partner
    ):
        """Prepare sale.order values from package data."""
        first_item = package_data.get("items", [{}])[0]
        order_number = str(first_item.get("orderNumber", ""))
        order_date = _parse_hb_datetime(package_data.get("orderDate"))
        cargo_company = package_data.get("cargoCompany", "")

        return self._prepare_base_order_values(
            backend,
            order_date,
            order_number,
            main_partner,
            shipping_partner,
            cargo_provider_name=cargo_company,
        )

    # ── Line Values ──────────────────────────────────────────────────────

    @api.model
    def _prepare_line_values(self, backend, sale_order, item):
        """Prepare sale.order.line values from HB package line item.

        Product matching cascade:
            productBarcode -> merchantSku -> hbSku -> fallback.
        """
        merchant_sku = item.get("merchantSku", "")
        hb_sku = item.get("hbSku", "")
        product_barcode = item.get("productBarcode", "")
        quantity = item.get("quantity", 1)

        # Get unit price from merchantUnitPrice or price
        price_data = item.get("merchantUnitPrice") or item.get("price", {})
        if isinstance(price_data, dict):
            price_unit = price_data.get("amount", 0)
        else:
            price_unit = price_data or 0

        # vat field is the VAT percentage (e.g. 20)
        vat_rate = item.get("vat", 0)

        # Calculate discount from unitHBDiscount + unitMerchantDiscount
        hb_discount_data = item.get("unitHBDiscount", {})
        merchant_discount_data = item.get("unitMerchantDiscount", {})
        hb_discount = (
            hb_discount_data.get("amount", 0)
            if isinstance(hb_discount_data, dict)
            else 0
        )
        merchant_discount = (
            merchant_discount_data.get("amount", 0)
            if isinstance(merchant_discount_data, dict)
            else 0
        )
        total_discount = hb_discount + merchant_discount

        # Product matching cascade
        Product = self.env["product.product"]
        product = False

        # 1. Match by productBarcode
        if product_barcode:
            product = Product.search([("barcode", "=", product_barcode)], limit=1)
        # 2. Match by merchantSku as barcode
        if not product and merchant_sku:
            product = Product.search([("barcode", "=", merchant_sku)], limit=1)
        # 3. Match by merchantSku as default_code
        if not product and merchant_sku:
            product = Product.search([("default_code", "=", merchant_sku)], limit=1)
        # 4. Match by hbSku as default_code
        if not product and hb_sku:
            product = Product.search([("default_code", "=", hb_sku)], limit=1)

        sku_info = merchant_sku or hb_sku or _("N/A")

        if product:
            line_name = product.display_name
        else:
            line_name = f"[{sku_info}] HB Item"

            if backend.default_product_id:
                product = backend.default_product_id
                _logger.info(
                    "Product not mapped for merchantSku %s / HBSKU %s "
                    "in order %s - using fallback product %s",
                    merchant_sku,
                    hb_sku,
                    sale_order.name,
                    product.display_name,
                )
            else:
                _logger.warning(
                    "Product not mapped for merchantSku %s / HBSKU %s "
                    "in order %s - creating note line",
                    merchant_sku,
                    hb_sku,
                    sale_order.name,
                )
                return {
                    "order_id": sale_order.id,
                    "display_type": "line_note",
                    "name": _(
                        "UNMAPPED: %(product)s (Qty: %(qty)s, Price: %(price)s)",
                        product=line_name,
                        qty=quantity,
                        price=price_unit,
                    ),
                }

        vals = {
            "order_id": sale_order.id,
            "name": line_name,
            "product_id": product.id,
            "product_uom_qty": quantity,
            "price_unit": price_unit,
        }

        # Convert absolute discount to percentage
        if total_discount and price_unit:
            vals["discount"] = (total_discount / price_unit) * 100

        # Find and apply matching tax
        tax = self._get_tax_for_rate(backend, vat_rate)
        if tax:
            vals["tax_id"] = [(6, 0, [tax.id])]

        return vals

    # ── Picking Notification ─────────────────────────────────────────────

    def _notify_picking_done(self, picking):
        """Notify Hepsiburada that a picking is done (set package intransit)."""
        self.ensure_one()

        if not self.hb_package_number:
            _logger.warning(
                "Cannot notify HB intransit for order %s: no package number",
                self.hb_order_number,
            )
            return

        client = self.backend_id._get_api_client()
        tracking_ref = picking.carrier_tracking_ref or ""

        data = {
            "packageNumber": self.hb_package_number,
            "shippedDate": fields.Datetime.now().isoformat(),
            "trackingInfoCode": tracking_ref,
        }

        try:
            client.set_package_intransit(data)
            self.hb_status = "in_transit"
            if tracking_ref and not self.cargo_tracking_number:
                self.cargo_tracking_number = tracking_ref
            _logger.info(
                "Notified HB intransit for order %s, package %s",
                self.hb_order_number,
                self.hb_package_number,
            )
        except HepsiburadaAPIError as e:
            _logger.error(
                "Failed to notify HB intransit for order %s: %s",
                self.hb_order_number,
                str(e),
            )
            raise

    # ── Tracking Fetch ────────────────────────────────────────────────────

    def action_fetch_tracking(self):
        """Manual button: fetch tracking info from Hepsiburada API."""
        self.ensure_one()
        if not self.hb_package_number:
            raise UserError(
                _("Cannot fetch tracking: no package number on this order.")
            )
        self._fetch_tracking_from_api()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Tracking Updated"),
                "message": _("Tracking info has been fetched from Hepsiburada."),
                "type": "success",
                "sticky": False,
            },
        }

    def _fetch_tracking_from_api(self):
        """Fetch package detail from HB API and update tracking fields."""
        self.ensure_one()
        if not self.hb_package_number:
            return

        client = self.backend_id._get_api_client()
        try:
            result = client.get_package_detail(self.hb_package_number)
        except HepsiburadaAPIError:
            _logger.warning(
                "Failed to fetch package detail for %s",
                self.hb_package_number,
                exc_info=True,
            )
            return

        # API returns a list; take the first element
        if isinstance(result, list):
            data = result[0] if result else {}
        else:
            data = result or {}

        vals = {}
        tracking_number = data.get("trackingInfoCode", "")
        tracking_url = data.get("trackingInfoUrl", "")
        cargo_company = data.get("cargoCompany", "")

        if tracking_number and not self.cargo_tracking_number:
            vals["cargo_tracking_number"] = tracking_number
        if tracking_url and not self.cargo_tracking_link:
            vals["cargo_tracking_link"] = tracking_url
        if cargo_company and not self.cargo_provider_name:
            vals["cargo_provider_name"] = cargo_company

        # Also update stock.picking carrier_tracking_ref
        if tracking_number:
            pickings = self.odoo_id.picking_ids.filtered(
                lambda p: (
                    p.picking_type_code == "outgoing" and not p.carrier_tracking_ref
                )
            )
            if pickings:
                pickings.write({"carrier_tracking_ref": tracking_number})

        if vals:
            self.write(vals)
            _logger.info(
                "Updated tracking for HB order %s: %s",
                self.hb_order_number,
                vals,
            )

    # ── Invoice Sending ──────────────────────────────────────────────────

    def action_send_invoice(self):
        """Manual button: queue invoice sending to Hepsiburada."""
        self.ensure_one()
        if self.invoice_link_sent:
            raise UserError(_("Invoice link already sent."))
        if self.hb_status == "cancelled":
            raise UserError(_("Cannot send invoice for cancelled orders."))
        if not self.odoo_id.invoice_ids.filtered(lambda i: i.state == "posted"):
            raise UserError(_("No posted invoice found for this order."))

        self.with_delay(
            channel="root.hepsiburada.order",
            description=_("Send invoice: %s") % self.hb_order_number,
        )._send_invoice()

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Invoice Send Queued"),
                "message": _("Invoice sending has been queued."),
                "type": "info",
                "sticky": False,
            },
        }

    def _send_invoice(self):
        """Send delivered status and invoice link to Hepsiburada API.

        Two-step process:
        1. Mark package as delivered via set_package_delivered()
        2. Upload invoice link via upload_invoice_link()
        """
        self.ensure_one()

        invoice = self.odoo_id.invoice_ids.filtered(
            lambda i: i.state == "posted" and i.move_type == "out_invoice"
        )[:1]

        if not invoice:
            _logger.warning(
                "No posted invoice found for HB order %s, skipping.",
                self.hb_order_number,
            )
            return

        client = self.backend_id._get_api_client()

        # Step 1: Mark package as delivered (if not already)
        if self.hb_status != "delivered" and self.hb_package_number:
            data = {
                "packageNumber": self.hb_package_number,
                "receivedDate": fields.Datetime.now().isoformat(),
                "receivedBy": self.hb_customer_name or "",
            }
            try:
                client.set_package_delivered(data)
                self.hb_status = "delivered"
            except HepsiburadaAPIError as e:
                if e.status_code == 409:
                    _logger.info(
                        "Package %s already delivered in HB, continuing.",
                        self.hb_package_number,
                    )
                    self.hb_status = "delivered"
                else:
                    _logger.error(
                        "Failed to set delivered for HB order %s: %s",
                        self.hb_order_number,
                        str(e),
                    )
                    raise

        # Step 2: Send invoice link
        if self.hb_package_number:
            base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url")
            invoice_url = f"{base_url}{invoice.get_portal_url()}"

            try:
                client.upload_invoice_link(self.hb_package_number, invoice_url)
            except HepsiburadaAPIError as e:
                if e.status_code == 409:
                    _logger.info(
                        "Invoice link already exists for HB order %s, "
                        "marking as sent locally.",
                        self.hb_order_number,
                    )
                else:
                    _logger.error(
                        "Failed to send invoice link for HB order %s: %s",
                        self.hb_order_number,
                        str(e),
                    )
                    raise

        self.invoice_link_sent = True
        self.invoice_sent_date = fields.Datetime.now()
        _logger.info(
            "Invoice link sent for HB order %s: %s",
            self.hb_order_number,
            invoice.name,
        )

    # ── Package Creation ─────────────────────────────────────────────────

    def action_create_package(self):
        """Manual button: queue package creation in Hepsiburada."""
        self.ensure_one()
        if self.hb_package_number:
            raise UserError(_("Package already created for this order."))
        if self.hb_status != "open":
            raise UserError(_("Only orders with 'Open' status can be packaged."))

        self.with_delay(
            channel="root.hepsiburada.order",
            description=_("Create package: %s") % self.hb_order_number,
        )._create_package()

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Package Creation Queued"),
                "message": _("Package creation has been queued."),
                "type": "info",
                "sticky": False,
            },
        }

    def _create_package(self):
        """Create a package in Hepsiburada for all line items."""
        self.ensure_one()

        client = self.backend_id._get_api_client()

        # Re-fetch order detail to get the real lineItemId values
        # The /orders list endpoint uses "id" but get_order_detail
        # may return the proper "lineItemId" field.
        detail = client.get_order_detail(self.hb_order_number)
        _logger.info(
            "Order detail response for %s: %s",
            self.hb_order_number,
            json.dumps(detail, default=str)[:2000],
        )

        detail_items = detail.get("items", [])
        if not detail_items:
            detail_items = detail if isinstance(detail, list) else []

        if not detail_items:
            raise UserError(_("No line items returned from order detail API."))

        line_item_requests = []
        for item in detail_items:
            # Prefer lineItemId over id — the /orders flat format uses "id"
            line_item_id = str(item.get("lineItemId") or item.get("id") or "")
            quantity = item.get("quantity", 1)
            if line_item_id:
                # HB API expects "id" key inside lineItemRequests, not "lineItemId"
                line_item_requests.append({"id": line_item_id, "quantity": quantity})

        if not line_item_requests:
            raise UserError(_("No valid line item IDs found in order detail."))

        _logger.info(
            "Creating package for HB order %s: items=%s",
            self.hb_order_number,
            line_item_requests,
        )

        try:
            result = client.create_package(line_item_requests)
        except HepsiburadaAPIError:
            _logger.error(
                "Failed to create package for HB order %s",
                self.hb_order_number,
                exc_info=True,
            )
            raise

        # Extract packageNumber from response
        actual_pkg = ""
        if isinstance(result, dict):
            actual_pkg = str(result.get("packageNumber", ""))
        elif isinstance(result, list) and result:
            first = result[0]
            if isinstance(first, dict):
                actual_pkg = str(first.get("packageNumber", ""))

        self.hb_package_number = actual_pkg
        self.hb_status = "packaged"
        _logger.info(
            "Created package %s for HB order %s",
            actual_pkg,
            self.hb_order_number,
        )

    # ── Order Cancellation ───────────────────────────────────────────────

    def action_cancel_in_hepsiburada(self):
        """Manual button: queue order cancellation in Hepsiburada."""
        self.ensure_one()
        if self.hb_status != "open":
            raise UserError(
                _("Only orders with 'Open' status can be cancelled in Hepsiburada.")
            )

        self.with_delay(
            channel="root.hepsiburada.order",
            description=_("Cancel order: %s") % self.hb_order_number,
        )._cancel_in_hepsiburada()

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

    def _cancel_in_hepsiburada(self):
        """Cancel all line items in Hepsiburada API."""
        self.ensure_one()

        client = self.backend_id._get_api_client()

        if not self.hb_line_item_ids:
            raise UserError(_("No line items found to cancel."))

        for line in self.hb_line_item_ids:
            try:
                client.cancel_line_item(line.hb_line_item_id)
            except HepsiburadaAPIError as e:
                _logger.error(
                    "Failed to cancel line item %s for HB order %s: %s",
                    line.hb_line_item_id,
                    self.hb_order_number,
                    str(e),
                )
                raise

        self.hb_status = "cancelled"

        if self.odoo_id.state not in ("done", "cancel"):
            self.odoo_id.with_context(
                from_hepsiburada_cancel=True,
                disable_cancel_warning=True,
            ).action_cancel()

        _logger.info("Cancelled HB order %s", self.hb_order_number)


class HepsiburadaOrderLine(models.Model):
    _name = "hepsiburada.order.line"
    _description = "Hepsiburada Order Line Item"

    hb_order_id = fields.Many2one(
        "hepsiburada.order",
        required=True,
        ondelete="cascade",
        index=True,
    )
    hb_line_item_id = fields.Char(
        string="HB Line Item ID",
        required=True,
        index=True,
        help="UUID from HB items[].id",
    )
    hb_sku = fields.Char(string="HBSKU")
    merchant_sku = fields.Char()
    sale_line_id = fields.Many2one("sale.order.line")
    product_id = fields.Many2one(
        related="sale_line_id.product_id",
        string="Product",
        store=True,
    )
    product_image = fields.Binary(
        related="product_id.image_128",
        string="Image",
    )
    quantity = fields.Integer()
    unit_price = fields.Float()
    total_price = fields.Float()
    vat_amount = fields.Float()
    vat_rate = fields.Float()
    commission_amount = fields.Float()
    status = fields.Char()

    _sql_constraints = [
        (
            "line_item_id_order_uniq",
            "unique(hb_line_item_id, hb_order_id)",
            "Line item ID must be unique per order!",
        ),
    ]
