# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import json
import logging

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)

INDIVIDUAL_VAT = "11111111111"


class HepsiburadaOrder(models.Model):
    _name = "hepsiburada.order"
    _description = "Hepsiburada Order"
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
        help="Customer display name from Hepsiburada order",
    )

    # Status (aggregated from line items)
    hb_status = fields.Selection(
        [
            ("open", "Open"),
            ("unpacked", "Unpacked"),
            ("packaged", "Packaged"),
            ("in_transit", "In Transit"),
            ("delivered", "Delivered"),
            ("cancelled", "Cancelled"),
            ("undelivered", "Undelivered"),
        ],
        default="open",
        required=True,
        index=True,
    )

    # Package info
    hb_package_number = fields.Char(string="Package Number")
    cargo_tracking_number = fields.Char(string="Tracking Number")
    cargo_tracking_link = fields.Char(string="Tracking Link")
    cargo_provider_name = fields.Char(string="Cargo Provider")

    # Delivery info from HB
    delivery_type = fields.Char(help="StandardDelivery / BT / YT")
    due_date = fields.Datetime(help="Last date to ship")

    # Raw data
    raw_data = fields.Text(help="Original JSON data from Hepsiburada")

    # Line item tracking for idempotency
    hb_line_item_ids = fields.One2many(
        "hepsiburada.order.line",
        "hb_order_id",
        string="HB Line Items",
    )

    _sql_constraints = [
        (
            "order_number_backend_uniq",
            "unique(hb_order_number, backend_id)",
            "Order number must be unique per backend!",
        ),
    ]

    @api.model
    def _import_order(self, backend, line_items_data):
        """Import a group of line items sharing the same orderNumber.

        Args:
            backend: hepsiburada.backend record.
            line_items_data: List of line item dicts from HB API
                (same orderNumber).

        Returns:
            hepsiburada.order record (created or existing).
        """
        if not line_items_data:
            return False

        first_item = line_items_data[0]
        order_number = str(first_item.get("orderNumber", ""))

        if not order_number:
            _logger.warning("HB line items missing orderNumber, skipping")
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
            # Add only NEW line items (idempotency)
            existing_line_ids = set(existing.hb_line_item_ids.mapped("hb_line_item_id"))
            new_items = [
                item
                for item in line_items_data
                if str(item.get("id", "")) not in existing_line_ids
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
                backend, first_item
            )
            order_vals = self._prepare_order_values(
                backend, first_item, main_partner, shipping_partner
            )
            sale_order = self.env["sale.order"].create(order_vals)

            # Extract cargo info from the first line item
            cargo_model = first_item.get("cargoCompanyModel", {})

            # Create binding before lines
            binding = self.create(
                {
                    "odoo_id": sale_order.id,
                    "backend_id": backend.id,
                    "hb_order_number": order_number,
                    "hb_order_id": str(first_item.get("orderId", "")),
                    "hb_customer_id": str(first_item.get("customerId", "")),
                    "hb_status": self._map_status(first_item.get("status")),
                    "cargo_provider_name": cargo_model.get("name", ""),
                    "hb_customer_name": first_item.get("customerName", ""),
                    "delivery_type": first_item.get("deliveryType", ""),
                    "due_date": first_item.get("dueDate"),
                    "raw_data": json.dumps(
                        line_items_data, indent=2, ensure_ascii=False
                    ),
                }
            )

            # Create order lines from all HB line items
            for item in line_items_data:
                self._add_line_to_order(backend, binding, item)

            # Auto-confirm if configured
            if backend.auto_confirm_orders:
                sale_order.ignore_exception = True
                sale_order.with_context(bypass_risk=True).action_confirm()

            _logger.info(
                "Imported HB order %s with %d line items",
                order_number,
                len(line_items_data),
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

        Args:
            backend: hepsiburada.backend record.
            binding: hepsiburada.order record.
            item: Line item dict from HB API.
        """
        line_item_id = str(item.get("id", ""))
        if not line_item_id:
            _logger.warning("HB line item missing id, skipping")
            return

        # Create sale.order.line
        line_vals = self._prepare_line_values(backend, binding.odoo_id, item)
        if not line_vals:
            return
        sale_line = self.env["sale.order.line"].create(line_vals)

        # Price fields
        unit_price_data = item.get("unitPrice", {})
        total_price_data = item.get("totalPrice", {})
        commission_data = item.get("commission", {})

        # Create tracking record
        self.env["hepsiburada.order.line"].create(
            {
                "hb_order_id": binding.id,
                "hb_line_item_id": line_item_id,
                "hb_sku": item.get("sku", ""),
                "merchant_sku": item.get("merchantSku", ""),
                "sale_line_id": sale_line.id,
                "quantity": item.get("quantity", 1),
                "unit_price": unit_price_data.get("amount", 0),
                "total_price": total_price_data.get("amount", 0),
                "vat_amount": item.get("vat", 0),
                "vat_rate": item.get("vatRate", 0),
                "commission_amount": commission_data.get("amount", 0),
                "status": item.get("status", ""),
            }
        )

    @api.model
    def _map_status(self, hb_status):
        """Map Hepsiburada status to our status field.

        Args:
            hb_status: Status string from API.

        Returns:
            Status selection value.
        """
        status_map = {
            "Open": "open",
            "Unpacked": "unpacked",
            "Packaged": "packaged",
            "InTransit": "in_transit",
            "Delivered": "delivered",
            "CancelledByMerchant": "cancelled",
            "CancelledByCustomer": "cancelled",
            "CancelledBySap": "cancelled",
            "ClaimCreated": "undelivered",
        }
        return status_map.get(hb_status, "open")

    @api.model
    def _get_or_create_partner(self, backend, item):
        """Get or create partner(s) from HB order line item data.

        Matching cascade:
        1. taxNumber (VKN) for commercial orders
        2. turkishIdentityNumber (TCKN) for individual orders
        3. hb_customer_id
        4. Create new partner

        Args:
            backend: hepsiburada.backend record.
            item: Line item dict from HB API.

        Returns:
            Tuple of (main_partner, shipping_partner) res.partner records.
        """
        main_partner = self._get_or_create_main_partner(backend, item)
        shipping_partner = self._get_or_create_shipping_partner(
            backend, item, main_partner
        )
        return main_partner, shipping_partner

    @api.model
    def _get_or_create_main_partner(self, backend, item):
        """Get or create main partner from HB invoice address.

        Args:
            backend: hepsiburada.backend record.
            item: Line item dict from HB API.

        Returns:
            res.partner record.
        """
        Partner = self.env["res.partner"]

        invoice = item.get("invoice", {})
        invoice_address = invoice.get("address", {})
        tax_number = (invoice.get("taxNumber") or "").strip()
        tckn = (invoice.get("turkishIdentityNumber") or "").strip()
        is_commercial = bool(tax_number) and tax_number != INDIVIDUAL_VAT

        # 1. Match by VKN (tax number) for commercial orders
        if is_commercial:
            partner = Partner.search(
                [
                    ("vat", "=", tax_number),
                    ("company_id", "in", [False, backend.company_id.id]),
                    ("parent_id", "=", False),
                ],
                limit=1,
            )
            if partner:
                return partner

        # 2. Match by TCKN for individual orders
        if tckn and tckn != INDIVIDUAL_VAT:
            partner = Partner.search(
                [
                    ("vat", "=", tckn),
                    ("company_id", "in", [False, backend.company_id.id]),
                    ("parent_id", "=", False),
                ],
                limit=1,
            )
            if partner:
                return partner

        # 3. Match by hb_customer_id
        customer_name = item.get("customerName", "")
        if customer_name:
            partner = Partner.search(
                [
                    ("hb_customer_id", "=", customer_name),
                    ("company_id", "in", [False, backend.company_id.id]),
                    ("parent_id", "=", False),
                ],
                limit=1,
            )
            if partner:
                return partner

        # 4. Create new partner from invoice address
        partner_vals = self._prepare_partner_values(
            backend, item, invoice_address, is_main=True
        )
        partner_vals["hb_customer_id"] = customer_name

        if is_commercial:
            partner_vals["vat"] = tax_number
            partner_vals["company_type"] = "company"
            tax_office = (invoice.get("taxOffice") or "").strip()
            if tax_office:
                partner_vals["tax_office_name"] = tax_office
        elif tckn:
            partner_vals["vat"] = tckn
        else:
            partner_vals["vat"] = INDIVIDUAL_VAT

        return Partner.create(partner_vals)

    @api.model
    def _get_or_create_shipping_partner(self, backend, item, main_partner):
        """Get or create shipping address as child partner.

        Args:
            backend: hepsiburada.backend record.
            item: Line item dict from HB API.
            main_partner: res.partner record (main/invoice partner).

        Returns:
            res.partner record (shipping address).
        """
        Partner = self.env["res.partner"]

        shipping_address = item.get("shippingAddress", {})
        shipping_addr_id = str(shipping_address.get("addressId", ""))

        # Try to find existing shipping address
        if shipping_addr_id:
            shipping_partner = Partner.search(
                [
                    ("hb_address_id", "=", shipping_addr_id),
                    ("parent_id", "=", main_partner.id),
                ],
                limit=1,
            )
            if shipping_partner:
                return shipping_partner

        # Create child partner for shipping address
        partner_vals = self._prepare_partner_values(
            backend, item, shipping_address, is_main=False
        )
        partner_vals["parent_id"] = main_partner.id
        partner_vals["type"] = "delivery"
        partner_vals["hb_address_id"] = shipping_addr_id

        return Partner.create(partner_vals)

    @api.model
    def _prepare_partner_values(self, backend, item, address, is_main=True):
        """Prepare partner values from HB address data.

        HB address fields:
        - name, address, email, phoneNumber, alternatePhoneNumber
        - district (mahalle), town (ilçe), city (şehir), countryCode

        Args:
            backend: hepsiburada.backend record.
            item: Line item dict from HB API.
            address: Address dict from HB API.
            is_main: True for main partner, False for child address.

        Returns:
            Dict of res.partner values.
        """
        full_name = (address.get("name") or "").strip()
        if not full_name:
            full_name = item.get("customerName", "").strip()
        if not full_name:
            full_name = _("Hepsiburada Customer")

        # Get country
        country_code = address.get("countryCode", "TR")
        country = self.env["res.country"].search([("code", "=", country_code)], limit=1)

        # Get state from city (Turkish provinces)
        state = False
        city = (address.get("city") or "").strip()
        if country and city:
            state = self.env["res.country.state"].search(
                [
                    ("country_id", "=", country.id),
                    "|",
                    ("name", "=ilike", city),
                    ("code", "=ilike", city),
                ],
                limit=1,
            )

        # Build street from address + district
        street = (address.get("address") or "").strip()
        district = (address.get("district") or "").strip()
        town = (address.get("town") or "").strip()

        # Use district as street2
        street2 = ""
        if district and town:
            street2 = f"{district} / {town}"
        elif district:
            street2 = district
        elif town:
            street2 = town

        partner_vals = {
            "name": full_name,
            "street": street,
            "street2": street2,
            "city": city,
            "phone": address.get("phoneNumber", ""),
            "email": address.get("email", ""),
            "country_id": country.id if country else False,
            "state_id": state.id if state else False,
            # Default to blacklisted to prevent accidental marketing emails
            "is_blacklisted": True,
        }

        if is_main:
            partner_vals["company_id"] = backend.company_id.id
            partner_vals["customer_rank"] = 1

        return partner_vals

    @api.model
    def _prepare_order_values(self, backend, item, main_partner, shipping_partner):
        """Prepare sale.order values from HB line item data.

        Args:
            backend: hepsiburada.backend record.
            item: First line item dict from HB API.
            main_partner: res.partner record (invoice partner).
            shipping_partner: res.partner record (delivery address).

        Returns:
            Dict of sale.order values.
        """
        order_date = item.get("orderDate")
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
            "client_order_ref": str(item.get("orderNumber", "")),
        }

        if backend.sales_team_id:
            vals["team_id"] = backend.sales_team_id.id
        if backend.fiscal_position_id:
            vals["fiscal_position_id"] = backend.fiscal_position_id.id
        if backend.source_id:
            vals["source_id"] = backend.source_id.id

        # Get carrier from cargo company mapping
        cargo_model = item.get("cargoCompanyModel", {})
        short_name = cargo_model.get("shortName", "")
        carrier = backend._get_carrier_for_cargo_provider(short_name)
        if carrier:
            vals["carrier_id"] = carrier.id

        return vals

    @api.model
    def _prepare_line_values(self, backend, sale_order, item):
        """Prepare sale.order.line values from HB line item.

        Product matching cascade: barcode → merchantSku → HBSKU → fallback.

        HB price fields:
        - unitPrice.amount: single item price (VAT included)
        - totalPrice.amount: quantity * unitPrice
        - vat: VAT amount
        - vatRate: VAT percentage

        Args:
            backend: hepsiburada.backend record.
            sale_order: sale.order record.
            item: Line item dict from HB API.

        Returns:
            Dict of sale.order.line values, or None.
        """
        merchant_sku = item.get("merchantSku", "")
        hb_sku = item.get("sku", "")
        quantity = item.get("quantity", 1)
        unit_price_data = item.get("unitPrice", {})
        price_unit = unit_price_data.get("amount", 0)
        vat_rate = item.get("vatRate", 0)

        # Product matching cascade
        Product = self.env["product.product"]
        product = False

        # 1. Match by barcode (merchantSku is often the barcode)
        if merchant_sku:
            product = Product.search([("barcode", "=", merchant_sku)], limit=1)
        # 2. Match by default_code
        if not product and merchant_sku:
            product = Product.search([("default_code", "=", merchant_sku)], limit=1)
        # 3. Match by HBSKU
        if not product and hb_sku:
            product = Product.search([("default_code", "=", hb_sku)], limit=1)

        # Build line description
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

        # Find and apply matching tax
        tax = self._get_tax_for_rate(backend, vat_rate)
        if tax:
            vals["tax_id"] = [(6, 0, [tax.id])]

        return vals

    @api.model
    def _get_tax_for_rate(self, backend, vat_rate):
        """Find sale tax matching the given VAT rate.

        Args:
            backend: hepsiburada.backend record.
            vat_rate: VAT rate percentage (e.g., 10, 20).

        Returns:
            account.tax record or False.
        """
        if not vat_rate:
            return False

        return self.env["account.tax"].search(
            [
                ("type_tax_use", "=", "sale"),
                ("amount", "=", vat_rate),
                ("price_include", "=", True),
                ("company_id", "=", backend.company_id.id),
            ],
            limit=1,
        )

    def _update_picking_delivery_state(self, hb_status):
        """Update stock.picking delivery_state from Hepsiburada status.

        Args:
            hb_status: Mapped status string (e.g., 'in_transit', 'delivered').
        """
        self.ensure_one()
        state_map = {
            "packaged": "shipping_recorded_in_carrier",
            "in_transit": "in_transit",
            "delivered": "customer_delivered",
            "cancelled": "canceled_shipment",
            "undelivered": "incident",
        }
        delivery_state = state_map.get(hb_status)
        if not delivery_state:
            return
        pickings = self.odoo_id.picking_ids.filtered(
            lambda p: p.picking_type_code == "outgoing"
        )
        for picking in pickings:
            vals = {"delivery_state": delivery_state}
            if hb_status == "in_transit":
                vals["date_shipped"] = fields.Date.today()
            if hb_status == "delivered":
                vals["date_delivered"] = fields.Datetime.now()
            picking.write(vals)

    def _notify_picking_done(self, picking):
        """Notify Hepsiburada that a picking is done (set package intransit).

        Called via queue_job when a stock.picking is validated.

        Args:
            picking: stock.picking record.
        """
        self.ensure_one()
        from .hepsiburada_request import HepsiburadaAPIError

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
        help="UUID from HB items[].id — unique per line item",
    )
    hb_sku = fields.Char(string="HBSKU", help="HBSKU from items[].sku")
    merchant_sku = fields.Char()
    sale_line_id = fields.Many2one("sale.order.line")
    quantity = fields.Integer()
    unit_price = fields.Float()
    total_price = fields.Float()
    vat_amount = fields.Float()
    vat_rate = fields.Float()
    commission_amount = fields.Float()
    status = fields.Char(help="Open/Unpacked/Packaged/etc.")

    _sql_constraints = [
        (
            "line_item_id_order_uniq",
            "unique(hb_line_item_id, hb_order_id)",
            "Line item ID must be unique per order!",
        ),
    ]
