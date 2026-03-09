# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import logging

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)

# Common VAT number for individual (non-commercial) customers in Turkey
INDIVIDUAL_VAT = "11111111111"


class MarketplaceOrder(models.AbstractModel):
    _name = "marketplace.order"
    _description = "Marketplace Order Base"
    _inherits = {"sale.order": "odoo_id"}
    _order = "create_date desc"

    odoo_id = fields.Many2one(
        "sale.order",
        string="Odoo Order",
        required=True,
        ondelete="cascade",
        index=True,
    )

    # Shipping info
    cargo_tracking_number = fields.Char(string="Tracking Number")
    cargo_tracking_link = fields.Char(string="Tracking Link")
    cargo_provider_name = fields.Char(string="Cargo Provider")

    # Invoice tracking
    invoice_link_sent = fields.Boolean(default=False)
    invoice_sent_date = fields.Datetime(readonly=True)

    # Raw API data
    raw_data = fields.Text()

    # ==================== Country / State Utilities ====================

    @api.model
    def _get_country(self, country_code):
        """Get country from country code (defaults to Turkey).

        Args:
            country_code: ISO 3166-1 alpha-2 country code

        Returns:
            res.country record or empty recordset
        """
        return self.env["res.country"].search(
            [("code", "=", country_code or "TR")], limit=1
        )

    @api.model
    def _get_state(self, country, city_name):
        """Get state/province from city name (case-insensitive).

        Args:
            country: res.country record
            city_name: City/province name string

        Returns:
            res.country.state record or None
        """
        if not country or not city_name:
            return None

        state = self.env["res.country.state"].search(
            [
                ("country_id", "=", country.id),
                "|",
                ("name", "=ilike", city_name),
                ("code", "=ilike", city_name),
            ],
            limit=1,
        )
        return state or None

    # ==================== Tax Utility ====================

    @api.model
    def _get_tax_for_rate(self, backend, vat_rate):
        """Find sale tax matching the given VAT rate (price-included).

        Marketplace prices are always VAT-included.

        Args:
            backend: marketplace.backend record
            vat_rate: VAT rate percentage (e.g., 10, 18, 20)

        Returns:
            account.tax record or None
        """
        if not vat_rate:
            return None

        return self.env["account.tax"].search(
            [
                ("type_tax_use", "=", "sale"),
                ("amount", "=", vat_rate),
                ("price_include", "=", True),
                ("company_id", "=", backend.company_id.id),
            ],
            limit=1,
        )

    # ==================== Partner Utilities ====================

    @api.model
    def _match_partner_by_vat(self, vat, company_id=None):
        """Search for existing partner by VAT number.

        Skips dummy individual VAT (11111111111).

        Args:
            vat: VAT/tax number string
            company_id: Optional company ID to filter by

        Returns:
            res.partner record or None
        """
        if not vat or vat == INDIVIDUAL_VAT:
            return None

        domain = [("vat", "=", vat), ("parent_id", "=", False)]
        if company_id:
            domain.append(("company_id", "in", [False, company_id]))

        return self.env["res.partner"].search(domain, limit=1) or None

    # ==================== Order Value Preparation ====================

    @api.model
    def _prepare_base_order_values(
        self,
        backend,
        order_date,
        order_number,
        main_partner,
        shipping_partner,
        cargo_provider_name=None,
    ):
        """Prepare common sale.order values shared by all marketplaces.

        Args:
            backend: marketplace.backend record
            order_date: Datetime for the order (or None for now())
            order_number: Marketplace order number (used as client_order_ref)
            main_partner: res.partner record (invoice partner)
            shipping_partner: res.partner record (delivery address)
            cargo_provider_name: Optional cargo provider name for carrier lookup

        Returns:
            Dict of sale.order values
        """
        vals = {
            "partner_id": main_partner.id,
            "partner_invoice_id": main_partner.id,
            "partner_shipping_id": shipping_partner.id,
            "date_order": order_date or fields.Datetime.now(),
            "company_id": backend.company_id.id,
            "warehouse_id": backend.warehouse_ids[:1].id,
            "pricelist_id": backend.pricelist_id.id,
            "client_order_ref": order_number,
        }

        if backend.sales_team_id:
            vals["team_id"] = backend.sales_team_id.id
        if backend.fiscal_position_id:
            vals["fiscal_position_id"] = backend.fiscal_position_id.id
        if backend.source_id:
            vals["source_id"] = backend.source_id.id

        if cargo_provider_name:
            carrier = backend._get_carrier_for_cargo_provider(cargo_provider_name)
            if carrier:
                vals["carrier_id"] = carrier.id

        return vals

    # ==================== Product Matching ====================

    @api.model
    def _find_product(self, search_keys):
        """Find a product by trying multiple search keys in order.

        Args:
            search_keys: List of (field_name, value) tuples to try.
                         e.g. [("barcode", "123"), ("default_code", "SKU1")]

        Returns:
            product.product record or None
        """
        Product = self.env["product.product"]
        for field_name, value in search_keys:
            if not value:
                continue
            product = Product.search([(field_name, "=", value)], limit=1)
            if product:
                return product
        return None

    @api.model
    def _prepare_unmapped_line(self, sale_order, sku_info, quantity, price_unit):
        """Create a note line for products that could not be mapped.

        Args:
            sale_order: sale.order record
            sku_info: SKU/barcode identifier string
            quantity: Order quantity
            price_unit: Unit price

        Returns:
            Dict of sale.order.line values (display_type='line_note')
        """
        return {
            "order_id": sale_order.id,
            "display_type": "line_note",
            "name": _(
                "UNMAPPED: %(product)s (Qty: %(qty)s, Price: %(price)s)",
                product=f"[{sku_info}]",
                qty=quantity,
                price=price_unit,
            ),
        }

    # ==================== Delivery State ====================

    def _update_picking_delivery_state(self, marketplace_status):
        """Update stock.picking delivery_state from marketplace status.

        Uses _get_delivery_state_map() hook for marketplace-specific mapping.

        Args:
            marketplace_status: Mapped marketplace status string
        """
        self.ensure_one()
        state_map = self._get_delivery_state_map()
        delivery_state = state_map.get(marketplace_status)
        if not delivery_state:
            return

        pickings = self.odoo_id.picking_ids.filtered(
            lambda p: p.picking_type_code == "outgoing"
        )
        for picking in pickings:
            vals = {"delivery_state": delivery_state}
            if delivery_state == "in_transit":
                vals["date_shipped"] = fields.Date.today()
            if delivery_state == "customer_delivered":
                vals["date_delivered"] = fields.Datetime.now()
            picking.write(vals)

    def _get_delivery_state_map(self):
        """Return dict mapping marketplace status to delivery_state values.

        Must be overridden by subclass.

        Returns:
            Dict like {"shipped": "in_transit", "delivered": "customer_delivered"}
        """
        raise NotImplementedError
