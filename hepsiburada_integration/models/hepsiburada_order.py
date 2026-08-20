# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import json
import logging
from hashlib import sha256

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .hepsiburada_backend import _parse_hb_datetime
from .hepsiburada_request import HepsiburadaAPIError

_logger = logging.getLogger(__name__)

INDIVIDUAL_VAT = "11111111111"


def _changed_values(record, vals):
    """Return the subset of ``vals`` that differs from the record.

    Empty values compare equal regardless of their falsy flavour, so an
    unchanged record is never rewritten.
    """
    changes = {}
    for field_name, value in vals.items():
        current = record[field_name]
        if isinstance(current, models.BaseModel):
            current = current.id
        if not current and not value:
            continue
        if current != value:
            changes[field_name] = value
    return changes


class HepsiburadaOrder(models.Model):
    _name = "hepsiburada.order"
    _description = "Hepsiburada Order"
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
    package_ids = fields.One2many(
        "hepsiburada.package",
        "hb_order_id",
        string="Packages",
    )
    package_count = fields.Integer(compute="_compute_package_count")
    package_mapping_incomplete = fields.Boolean(
        readonly=True,
        index=True,
    )

    # Delivery info
    delivery_type = fields.Char(help="StandardDelivery / BT / YT")
    due_date = fields.Datetime(help="Last date to ship")
    is_overdue = fields.Boolean(
        compute="_compute_is_overdue",
        search="_search_is_overdue",
    )

    # Shipping info
    cargo_tracking_number = fields.Char(string="Tracking Number")
    cargo_tracking_link = fields.Char(string="Tracking Link")
    cargo_provider_name = fields.Char(string="Cargo Provider")

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
    invoice_link_sent = fields.Boolean(default=False)
    invoice_sent_date = fields.Datetime(readonly=True)

    # Raw data
    raw_data = fields.Text(help="Original JSON data from Hepsiburada")

    _sql_constraints = [
        (
            "order_number_backend_uniq",
            "unique(hb_order_number, backend_id)",
            "Order number must be unique per backend!",
        ),
    ]

    def _marketplace_order_number(self):
        return self.hb_order_number

    @api.depends("package_ids")
    def _compute_package_count(self):
        for order in self:
            order.package_count = len(order.package_ids)

    def _marketplace_delivery_state_map(self):
        return {
            "packaged": "shipping_recorded_in_carrier",
            "in_transit": "in_transit",
            "delivered": "customer_delivered",
            "cancelled": "canceled_shipment",
            "undelivered": "incident",
        }

    def _marketplace_shipped_statuses(self):
        return ("in_transit",)

    def _marketplace_delivered_statuses(self):
        return ("delivered",)

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
            return self._update_existing_order(backend, existing, package_data)

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
            initial_status = package_data.get("_hb_status") or self._map_status(
                package_data.get("status")
            )
            binding = self.create(
                {
                    "odoo_id": sale_order.id,
                    "backend_id": backend.id,
                    "hb_order_number": order_number,
                    "hb_order_id": str(
                        first_item.get("orderId") or package_data.get("orderId") or ""
                    ),
                    "hb_customer_id": str(package_data.get("customerId") or ""),
                    "hb_status": initial_status or "open",
                    "cargo_provider_name": package_data.get("cargoCompany", ""),
                    "hb_customer_name": package_data.get("customerName", ""),
                    "hb_full_address": full_address,
                    "delivery_type": first_item.get("deliveryType", ""),
                    "due_date": _parse_hb_datetime(package_data.get("dueDate")),
                    "raw_data": json.dumps(package_data, indent=2, ensure_ascii=False),
                }
            )

            package = binding._upsert_package(package_data, initial_status)

            # Create order lines from all HB line items
            for item in line_items:
                self._add_line_to_order(
                    backend,
                    binding,
                    item,
                    package=package,
                    status=initial_status,
                )

            # Auto-confirm if configured
            if backend.auto_confirm_orders and binding.hb_status not in (
                "cancelled",
                "payment_awaiting",
            ):
                sale_order.ignore_exception = True
                sale_order.with_context(bypass_risk=True).action_confirm()
            elif binding.hb_status == "cancelled":
                sale_order.with_context(
                    from_hepsiburada_cancel=True,
                    disable_cancel_warning=True,
                ).action_cancel()

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

    @api.model
    def _update_existing_order(self, backend, existing, package_data):
        """Refresh an already imported order from a package payload."""
        line_items = package_data.get("items", [])
        new_status = package_data.get("_hb_status") or self._map_status(
            package_data.get("status")
        )
        status_scope = package_data.get("_status_scope", "order")
        # A line-scoped cancellation only cancels the listed line items:
        # the package itself must keep its current status.
        line_cancellation = status_scope == "line" and new_status == "cancelled"
        raw_data = json.dumps(package_data, indent=2, ensure_ascii=False)
        if existing.raw_data != raw_data:
            existing.raw_data = raw_data
        package = existing._upsert_package(
            package_data,
            None if line_cancellation else new_status,
        )

        existing_lines = {
            line.hb_line_item_id: line for line in existing.hb_line_item_ids
        }
        added_count = 0
        for item in line_items:
            line_item_id = str(item.get("lineItemId") or item.get("id") or "")
            if not line_item_id:
                continue
            line = existing_lines.get(line_item_id)
            if line:
                line._update_from_api(item, package=package, status=new_status)
                continue
            self._add_line_to_order(
                backend,
                existing,
                item,
                package=package,
                status=new_status,
            )
            added_count += 1

        if added_count:
            _logger.info(
                "Added %d new line items to existing HB order %s",
                added_count,
                existing.hb_order_number,
            )

        if line_cancellation:
            existing._sync_status_from_lines()
        elif package:
            existing._sync_from_packages()
        elif new_status and not existing.package_ids:
            existing._set_order_status(new_status)
        existing._refresh_shipping_partner(package_data)
        return existing

    def _add_line_to_order(self, backend, binding, item, package=False, status=None):
        """Add a single HB line item to the order.

        Creates both the sale.order.line and the
        hepsiburada.order.line tracking record.
        """
        line_item_id = str(item.get("lineItemId") or item.get("id") or "")
        if not line_item_id:
            _logger.warning("HB line item missing lineItemId, skipping")
            return

        line_vals = self._prepare_line_values(backend, binding.odoo_id, item)
        if not line_vals:
            return
        sale_line = self.env["sale.order.line"].create(line_vals)
        if status == "cancelled":
            sale_line.product_uom_qty = 0

        HbLine = self.env["hepsiburada.order.line"]
        hb_line_vals = HbLine._hb_line_vals_from_item(item)
        hb_line_vals.update(
            {
                "hb_order_id": binding.id,
                "package_id": package.id if package else False,
                "hb_line_item_id": line_item_id,
                "sale_line_id": sale_line.id,
                "status": status or binding.hb_status,
            }
        )
        HbLine.create(hb_line_vals)

    def _upsert_package(self, package_data, status=None):
        self.ensure_one()
        package_number = package_data.get("packageNumber")
        if package_number in (None, "", False):
            return self.env["hepsiburada.package"]
        package_number = str(package_number)
        package = self.env["hepsiburada.package"].search(
            [
                ("backend_id", "=", self.backend_id.id),
                ("hb_package_number", "=", package_number),
            ],
            limit=1,
        )
        if package and package.hb_order_id != self:
            raise UserError(
                _("Package %(package)s is already linked to order %(order)s.")
                % {
                    "package": package_number,
                    "order": package.hb_order_id.hb_order_number,
                }
            )
        if not package:
            package = self.env["hepsiburada.package"].create(
                {
                    "hb_order_id": self.id,
                    "hb_package_number": package_number,
                    "hb_status": status
                    if status
                    in (
                        "packaged",
                        "in_transit",
                        "delivered",
                        "undelivered",
                        "cancelled",
                    )
                    else "packaged",
                }
            )
        package_status = (
            status
            if status
            in ("packaged", "in_transit", "delivered", "undelivered", "cancelled")
            else package.hb_status
        )
        package._update_from_api(package_data, status=package_status)
        return package

    def _set_order_status(self, status):
        self.ensure_one()
        if not status or self.hb_status == status:
            return
        self.hb_status = status
        self._update_picking_delivery_state(status)
        if status == "cancelled" and self.odoo_id.state not in ("done", "cancel"):
            self.odoo_id.with_context(
                from_hepsiburada_cancel=True,
                disable_cancel_warning=True,
            ).action_cancel()

    def _sync_status_from_lines(self):
        self.ensure_one()
        statuses = set(self.hb_line_item_ids.mapped("status"))
        if statuses and statuses == {"cancelled"}:
            self._set_order_status("cancelled")

    def _sync_from_packages(self):
        for order in self:
            packages = order.package_ids
            active_packages = packages.filtered(
                lambda package: package.hb_status != "cancelled"
            )
            statuses = set(active_packages.mapped("hb_status"))
            if packages and not active_packages:
                aggregate_status = "cancelled"
            elif statuses and statuses == {"delivered"}:
                aggregate_status = "delivered"
            elif "undelivered" in statuses:
                aggregate_status = "undelivered"
            elif statuses & {"in_transit", "delivered"}:
                aggregate_status = "in_transit"
            elif statuses:
                aggregate_status = "packaged"
            else:
                aggregate_status = False

            vals = {
                "package_mapping_incomplete": bool(
                    packages
                    and order.hb_line_item_ids.filtered(
                        lambda line: not line.package_id and line.status != "cancelled"
                    )
                ),
            }
            # Invoice flags are owned by the packages. Orders without package
            # records own them directly, so leave those untouched here.
            if packages:
                vals.update(
                    {
                        "hb_missing_invoice": any(
                            packages.mapped("hb_missing_invoice")
                        ),
                        "invoice_link_sent": all(packages.mapped("invoice_link_sent")),
                        "invoice_sent_date": max(
                            (
                                date
                                for date in packages.mapped("invoice_sent_date")
                                if date
                            ),
                            default=False,
                        ),
                    }
                )
            if len(packages) == 1:
                package = packages[0]
                vals.update(
                    {
                        "hb_package_number": package.hb_package_number,
                        "hb_cargo_barcode": package.hb_cargo_barcode,
                        "cargo_provider_name": package.cargo_provider_name,
                        "cargo_tracking_number": package.cargo_tracking_number,
                        "cargo_tracking_link": package.cargo_tracking_link,
                    }
                )
            elif len(packages) > 1:
                vals.update(
                    {
                        "hb_package_number": False,
                        "hb_cargo_barcode": False,
                        "cargo_tracking_number": False,
                        "cargo_tracking_link": False,
                    }
                )
            changes = _changed_values(order, vals)
            if changes:
                order.write(changes)
            if aggregate_status:
                order._set_order_status(aggregate_status)
            order._propagate_tracking_to_pickings()

    def _propagate_tracking_to_pickings(self):
        """Stamp the HB tracking number on outgoing pickings missing one."""
        self.ensure_one()
        if not self.cargo_tracking_number:
            return
        pickings = self.odoo_id.picking_ids.filtered(
            lambda picking: (
                picking.picking_type_code == "outgoing"
                and not picking.carrier_tracking_ref
            )
        )
        if pickings:
            pickings.write({"carrier_tracking_ref": self.cargo_tracking_number})

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
        return status_map.get(hb_status)

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
        customer_id = str(pkg.get("customerId") or "")
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

        address_id = str(pkg.get("shippingAddressId") or "").strip()
        if not address_id:
            address_parts = [
                pkg.get("recipientName"),
                pkg.get("shippingAddressDetail"),
                pkg.get("shippingDistrict"),
                pkg.get("shippingTown"),
                pkg.get("shippingCity"),
                pkg.get("shippingPostalCode"),
                pkg.get("shippingCountryCode"),
            ]
            normalized_address = "|".join(
                " ".join(str(part or "").lower().split()) for part in address_parts
            )
            if normalized_address.strip("|"):
                address_id = (
                    "address:" + sha256(normalized_address.encode("utf-8")).hexdigest()
                )

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
            "zip": (pkg.get("shippingPostalCode") or "").strip(),
            "phone": pkg.get("phoneNumber", ""),
            "email": pkg.get("email", ""),
            "country_id": country.id if country else False,
            "state_id": state.id if state else False,
            "is_blacklisted": True,
            "hb_address_id": address_id or False,
        }

        # Refresh the stored address: HB may change it under a stable id.
        if address_id:
            shipping_partner = Partner.search(
                [
                    ("hb_address_id", "=", address_id),
                    ("parent_id", "=", main_partner.id),
                    ("type", "=", "delivery"),
                ],
                limit=1,
            )
            if shipping_partner:
                changes = _changed_values(shipping_partner, partner_vals)
                # Computed without inverse: writing it is a silent no-op, so
                # it would show up as a change on every single re-import.
                changes.pop("is_blacklisted", None)
                if changes:
                    shipping_partner.write(changes)
                return shipping_partner
        return Partner.create(partner_vals)

    def _refresh_shipping_partner(self, package_data):
        self.ensure_one()
        if not package_data.get("shippingAddressDetail"):
            return
        main_partner = self.odoo_id.partner_id
        shipping_partner = self._get_or_create_shipping_partner(
            self.backend_id,
            package_data,
            main_partner,
        )
        if self.odoo_id.partner_shipping_id != shipping_partner:
            self.odoo_id.partner_shipping_id = shipping_partner

    @api.model
    def _get_country(self, country_code):
        """Get country from country code (defaults to Turkey)."""
        return self._get_country_by_code(country_code)

    @api.model
    def _get_state(self, country, city_name):
        """Get state/province from city name."""
        return self._get_state_by_name(country, city_name)

    # ── Order Values ─────────────────────────────────────────────────────

    @api.model
    def _prepare_order_values(
        self, backend, package_data, main_partner, shipping_partner
    ):
        """Prepare sale.order values from package data."""
        first_item = package_data.get("items", [{}])[0]
        order_number = str(first_item.get("orderNumber", ""))
        return self._prepare_marketplace_order_values(
            backend,
            main_partner,
            shipping_partner,
            _parse_hb_datetime(package_data.get("orderDate")) or fields.Datetime.now(),
            order_number,
            cargo_provider_name=package_data.get("cargoCompany", ""),
        )

    # ── Line Values ──────────────────────────────────────────────────────

    @api.model
    def _prepare_line_values(self, backend, sale_order, item):
        """Prepare sale.order.line values from HB package line item.

        Product matching cascade:
            productBarcode -> merchantSku -> normalized merchantSku -> hbSku
            -> fallback.
        """
        merchant_sku = str(item.get("merchantSku") or "").strip()
        hb_sku = str(item.get("hbSku") or "").strip()
        product_barcode = str(item.get("productBarcode") or "").strip()
        quantity = item.get("quantity", 1)

        # Get unit price from merchantUnitPrice or price
        price_data = item.get("merchantUnitPrice") or item.get("price", {})
        if isinstance(price_data, dict):
            price_unit = price_data.get("amount", 0)
        else:
            price_unit = price_data or 0

        # vatRate is the VAT percentage (e.g. 10, 20); vat is the VAT amount in TL
        vat_rate = item.get("vatRate")
        if vat_rate in (None, ""):
            vat_rate = backend.default_vat_rate

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

        # 4. Hepsiburada listings may contain Odoo's display-name form, e.g.
        # ``[PC-278-0-0-S-0]``, instead of the raw default code. Only use the
        # unwrapped value when it identifies a single product.
        normalized_merchant_sku = merchant_sku
        if merchant_sku.startswith("[") and merchant_sku.endswith("]"):
            normalized_merchant_sku = merchant_sku[1:-1].strip()
        if (
            not product
            and normalized_merchant_sku
            and normalized_merchant_sku != merchant_sku
        ):
            candidates = Product.search(
                [("default_code", "=", normalized_merchant_sku)], limit=2
            )
            if len(candidates) == 1:
                product = candidates
            elif candidates:
                _logger.warning(
                    "Ambiguous normalized merchantSku %s for order %s",
                    normalized_merchant_sku,
                    sale_order.name,
                )

        # 5. Match by hbSku as default_code
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
                return self._prepare_unmapped_line_values(
                    sale_order,
                    line_name,
                    quantity,
                    price_unit,
                )

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

    @api.model
    def _get_tax_for_rate(self, backend, vat_rate):
        """Find sale tax matching the given VAT rate."""
        return super()._get_tax_for_rate(backend, vat_rate)

    # ── Picking Delivery State ───────────────────────────────────────────

    def _update_picking_delivery_state(self, hb_status):
        """Update stock.picking delivery_state from Hepsiburada status."""
        return super()._update_picking_delivery_state(hb_status)

    # ── Tracking Fetch ────────────────────────────────────────────────────

    def action_fetch_tracking(self):
        """Manual button: fetch tracking info from Hepsiburada API."""
        self.ensure_one()
        self._ensure_package_records()
        if not self.package_ids:
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
        """Fetch every HB package independently and refresh aggregate fields."""
        self.ensure_one()
        self._ensure_package_records()
        if not self.package_ids:
            return
        errors = []
        for package in self.package_ids:
            try:
                package._fetch_tracking_from_api()
            except HepsiburadaAPIError as error:
                errors.append(str(error))
                _logger.warning(
                    "Failed to fetch HB package detail for %s",
                    package.hb_package_number,
                    exc_info=True,
                )
        self._sync_from_packages()
        if errors and len(errors) == len(self.package_ids):
            raise UserError(_("Tracking could not be fetched: %s") % errors[0])

    def _ensure_package_records(self):
        """Create the package child for records predating the package model."""
        for order in self:
            if order.package_ids or not order.hb_package_number:
                continue
            package = self.env["hepsiburada.package"].create(
                {
                    "hb_order_id": order.id,
                    "hb_package_number": order.hb_package_number,
                    "hb_status": order.hb_status
                    if order.hb_status
                    in (
                        "packaged",
                        "in_transit",
                        "delivered",
                        "undelivered",
                        "cancelled",
                    )
                    else "packaged",
                    "hb_cargo_barcode": order.hb_cargo_barcode,
                    "cargo_provider_name": order.cargo_provider_name,
                    "cargo_tracking_number": order.cargo_tracking_number,
                    "cargo_tracking_link": order.cargo_tracking_link,
                    "hb_missing_invoice": order.hb_missing_invoice,
                    "invoice_link_sent": order.invoice_link_sent,
                    "invoice_sent_date": order.invoice_sent_date,
                    "raw_data": order.raw_data,
                }
            )
            try:
                raw_data = json.loads(order.raw_data or "{}")
            except (TypeError, ValueError):
                raw_data = {}
            raw_line_ids = {
                str(item.get("lineItemId") or item.get("id") or "")
                for item in raw_data.get("items", [])
            }
            lines = order.hb_line_item_ids.filtered(
                lambda line: (
                    not line.package_id
                    and line.status != "cancelled"
                    and (not raw_line_ids or line.hb_line_item_id in raw_line_ids)
                )
            )
            lines.write({"package_id": package.id})
            order._sync_from_packages()

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
        """Upload the invoice link to Hepsiburada for this order.

        Hepsiburada does not allow a merchant to set delivery status (the
        carrier owns it; attempting it returns 403
        DeliveryManipulationForbiddenError), so this only uploads the invoice
        link. Delivery status is maintained separately by the import cron.
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

        self._ensure_package_records()
        if not self.package_ids:
            _logger.warning(
                "No package number for HB order %s, skipping invoice mark.",
                self.hb_order_number,
            )
            return

        base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url")
        invoice_url = f"{base_url}{invoice.get_portal_url()}"
        for package in self.package_ids.filtered(
            lambda item: not item.invoice_link_sent
        ):
            package._send_invoice_link(invoice_url)
        self._sync_from_packages()
        _logger.info(
            "Invoice link sent for HB order %s: %s",
            self.hb_order_number,
            invoice.name,
        )

    # ── Package Creation ─────────────────────────────────────────────────

    def action_create_package(self):
        """Manual button: queue package creation in Hepsiburada."""
        self.ensure_one()
        self._ensure_package_records()
        if self.package_ids:
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
        detail_items = detail if isinstance(detail, list) else detail.get("items", [])

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

        if not actual_pkg:
            raise UserError(
                _("Hepsiburada created the package but returned no package number.")
            )
        package_data = {
            "packageNumber": actual_pkg,
            "items": detail_items,
            "status": "Packaged",
        }
        package = self._upsert_package(package_data, "packaged")
        line_by_id = {line.hb_line_item_id: line for line in self.hb_line_item_ids}
        for item in detail_items:
            line_item_id = str(item.get("lineItemId") or item.get("id") or "")
            if line_item_id in line_by_id:
                line_by_id[line_item_id]._update_from_api(
                    item,
                    package=package,
                    status="packaged",
                )
        self._sync_from_packages()
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
                if e.status_code == 409:
                    line.status = "cancelled"
                    continue
                _logger.error(
                    "Failed to cancel line item %s for HB order %s: %s",
                    line.hb_line_item_id,
                    self.hb_order_number,
                    str(e),
                )
                raise
            line.status = "cancelled"

        self._sync_status_from_lines()

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
    package_id = fields.Many2one(
        "hepsiburada.package",
        ondelete="set null",
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
    quantity = fields.Integer()
    unit_price = fields.Float()
    total_price = fields.Float()
    vat_amount = fields.Float()
    vat_rate = fields.Float()
    commission_amount = fields.Float()
    status = fields.Char()

    @staticmethod
    def _item_amount(value):
        """Unwrap Hepsiburada's {currency, amount} money objects."""
        if isinstance(value, dict):
            return value.get("amount", 0)
        return value or 0

    def _hb_line_vals_from_item(self, item):
        """Extract the shared line values from an HB API item payload.

        Called on an existing line the stored values are used as fallbacks for
        keys the payload does not carry; called on an empty recordset the
        creation defaults apply.
        """
        line = self[:1]
        return {
            "hb_sku": item.get("hbSku") or item.get("sku") or line.hb_sku or "",
            "merchant_sku": item.get("merchantSku")
            or item.get("merchantSKU")
            or line.merchant_sku
            or "",
            "quantity": item.get("quantity", line.quantity if line else 1),
            "unit_price": self._item_amount(item.get("price")),
            "total_price": self._item_amount(item.get("totalPrice")),
            "vat_amount": item.get("vat", line.vat_amount),
            "vat_rate": item.get("vatRate", line.vat_rate),
            "commission_amount": self._item_amount(item.get("commission")),
        }

    def _update_from_api(self, item, package=False, status=None):
        self.ensure_one()
        vals = self._hb_line_vals_from_item(item)
        vals["package_id"] = package.id if package else self.package_id.id
        if status:
            vals["status"] = status
        self.write(vals)
        if (
            status == "cancelled"
            and self.sale_line_id
            and not self.sale_line_id.qty_delivered
            and not self.sale_line_id.qty_invoiced
        ):
            self.sale_line_id.product_uom_qty = 0

    _sql_constraints = [
        (
            "line_item_id_order_uniq",
            "unique(hb_line_item_id, hb_order_id)",
            "Line item ID must be unique per order!",
        ),
    ]
