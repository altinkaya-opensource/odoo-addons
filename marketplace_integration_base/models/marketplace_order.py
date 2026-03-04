# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

# Turkish individual VAT number placeholder (used for unmapped customers)
INDIVIDUAL_VAT = "11111111111"


class MarketplaceOrder(models.AbstractModel):
    _name = "marketplace.order"
    _description = "Marketplace Order"

    # -- Shipping info --
    cargo_tracking_number = fields.Char(string="Tracking Number")
    cargo_tracking_link = fields.Char(string="Tracking Link")
    cargo_provider_name = fields.Char(string="Cargo Provider")

    # -- Raw API data --
    raw_data = fields.Text(
        help="Original JSON data from the marketplace",
    )

    # -----------------------------------------------------------------
    # Tax helper
    # -----------------------------------------------------------------

    @api.model
    def _get_tax_for_rate(self, backend, vat_rate):
        """Find sale tax matching the given VAT rate.

        Searches for a price-included sale tax with the exact rate
        in the backend's company.

        Args:
            backend: marketplace.backend record.
            vat_rate: VAT rate percentage (e.g., 10, 18, 20).

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

    # -----------------------------------------------------------------
    # Address / geography helpers
    # -----------------------------------------------------------------

    @api.model
    def _get_country(self, address):
        """Get country from address data.

        Defaults to Turkey (TR) if no country code is provided.

        Args:
            address: Address dict from marketplace API.

        Returns:
            res.country record or empty recordset.
        """
        country_code = address.get("countryCode", "TR")
        return self.env["res.country"].search([("code", "=", country_code)], limit=1)

    @api.model
    def _get_state(self, country, address):
        """Get state/province from address data (Turkish provinces).

        Matches the city name against res.country.state name or code
        (case-insensitive).

        Args:
            country: res.country record.
            address: Address dict from marketplace API.

        Returns:
            res.country.state record or False.
        """
        if not country:
            return False

        city = (address.get("city") or "").strip()
        if not city:
            return False

        return self.env["res.country.state"].search(
            [
                ("country_id", "=", country.id),
                "|",
                ("name", "=ilike", city),
                ("code", "=ilike", city),
            ],
            limit=1,
        )

    # -----------------------------------------------------------------
    # Order value preparation
    # -----------------------------------------------------------------

    @api.model
    def _prepare_order_values(
        self, backend, order_data, main_partner, shipping_partner
    ):
        """Prepare base sale.order values common to all marketplaces.

        Sets partner, company, warehouse, pricelist, team, fiscal
        position, source, and marks the order as a marketplace order.

        Concrete models should call super() and add marketplace-specific
        values (date_order, client_order_ref, carrier_id).

        Args:
            backend: marketplace.backend record.
            order_data: Dict from marketplace API.
            main_partner: res.partner record (invoice partner).
            shipping_partner: res.partner record (delivery address).

        Returns:
            Dict of sale.order values.
        """
        vals = {
            "partner_id": main_partner.id,
            "partner_invoice_id": main_partner.id,
            "partner_shipping_id": shipping_partner.id,
            "company_id": backend.company_id.id,
            "warehouse_id": backend.warehouse_ids[:1].id,
            "pricelist_id": backend.pricelist_id.id,
            "is_marketplace_order": True,
        }

        if backend.sales_team_id:
            vals["team_id"] = backend.sales_team_id.id
        if backend.fiscal_position_id:
            vals["fiscal_position_id"] = backend.fiscal_position_id.id
        if backend.source_id:
            vals["source_id"] = backend.source_id.id

        return vals

    # -----------------------------------------------------------------
    # Delivery state management
    # -----------------------------------------------------------------

    def _get_delivery_state_mapping(self):
        """Return a dict mapping marketplace status to OCA delivery_state.

        Must be overridden by each concrete marketplace order model.

        Returns:
            Dict[str, str]: marketplace_status -> delivery_state value.
        """
        return {}

    def _get_shipped_status(self):
        """Return the marketplace status value that means 'shipped/in transit'.

        Used by _update_picking_delivery_state to set date_shipped.

        Returns:
            str: The shipped status key, or empty string.
        """
        return ""

    def _get_delivered_status(self):
        """Return the marketplace status value that means 'delivered'.

        Used by _update_picking_delivery_state to set date_delivered.

        Returns:
            str: The delivered status key, or empty string.
        """
        return ""

    def _update_picking_delivery_state(self, marketplace_status):
        """Update stock.picking delivery_state from marketplace status.

        Maps marketplace status to OCA delivery_state values using
        _get_delivery_state_mapping() and writes to outgoing pickings.

        Args:
            marketplace_status: Mapped status string.
        """
        self.ensure_one()
        state_map = self._get_delivery_state_mapping()
        delivery_state = state_map.get(marketplace_status)
        if not delivery_state:
            return

        pickings = self.odoo_id.picking_ids.filtered(
            lambda p: p.picking_type_code == "outgoing"
        )
        for picking in pickings:
            vals = {"delivery_state": delivery_state}
            if marketplace_status == self._get_shipped_status():
                vals["date_shipped"] = fields.Date.today()
            if marketplace_status == self._get_delivered_status():
                vals["date_delivered"] = fields.Datetime.now()
            picking.write(vals)
