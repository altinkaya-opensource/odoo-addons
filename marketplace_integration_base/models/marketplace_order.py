# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import _, fields, models

INDIVIDUAL_VAT = "11111111111"


class MarketplaceOrderMixin(models.AbstractModel):
    _name = "marketplace.order.mixin"
    _description = "Marketplace Order Mixin"

    cargo_tracking_number = fields.Char(string="Tracking Number")
    cargo_tracking_link = fields.Char(string="Tracking Link")
    cargo_provider_name = fields.Char(string="Cargo Provider")
    invoice_link_sent = fields.Boolean(default=False)
    invoice_sent_date = fields.Datetime(readonly=True)
    raw_data = fields.Text(help="Original JSON data from marketplace API")

    def _marketplace_order_number(self):
        return self.display_name

    def _marketplace_delivery_state_map(self):
        return {}

    def _marketplace_shipped_statuses(self):
        return ()

    def _marketplace_delivered_statuses(self):
        return ()

    def _marketplace_queue_channel(self):
        return self.backend_id._marketplace_queue_channel()

    def _marketplace_notification(
        self,
        title,
        message,
        notification_type="info",
        sticky=False,
    ):
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": title,
                "message": message,
                "type": notification_type,
                "sticky": sticky,
            },
        }

    def _get_country_by_code(self, country_code="TR"):
        Country = self.env["res.country"]
        return Country.search([("code", "=", country_code or "TR")], limit=1)

    def _get_state_by_name(self, country, city_name):
        if not country or not city_name:
            return None

        State = self.env["res.country.state"]
        return (
            State.search(
                [
                    ("country_id", "=", country.id),
                    "|",
                    ("name", "=ilike", city_name),
                    ("code", "=ilike", city_name),
                ],
                limit=1,
            )
            or None
        )

    def _prepare_marketplace_order_values(
        self,
        backend,
        main_partner,
        shipping_partner,
        date_order,
        client_order_ref,
        cargo_provider_name=None,
    ):
        vals = {
            "partner_id": main_partner.id,
            "partner_invoice_id": main_partner.id,
            "partner_shipping_id": shipping_partner.id,
            "date_order": date_order or fields.Datetime.now(),
            "company_id": backend.company_id.id,
            "warehouse_id": backend.warehouse_ids[:1].id,
            "pricelist_id": backend.pricelist_id.id,
            "client_order_ref": client_order_ref,
        }

        if backend.sales_team_id:
            vals["team_id"] = backend.sales_team_id.id
        if backend.fiscal_position_id:
            vals["fiscal_position_id"] = backend.fiscal_position_id.id
        if backend.source_id:
            vals["source_id"] = backend.source_id.id

        carrier = backend._get_carrier_for_cargo_provider(cargo_provider_name)
        if carrier:
            vals["carrier_id"] = carrier.id

        return vals

    def _prepare_unmapped_line_values(
        self, sale_order, line_name, quantity, price_unit
    ):
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

    def _get_tax_for_rate(self, backend, vat_rate):
        """Find sale tax matching a VAT rate."""
        if not vat_rate:
            return None

        Tax = self.env["account.tax"]
        return Tax.search(
            [
                ("type_tax_use", "=", "sale"),
                ("amount", "=", vat_rate),
                ("price_include", "=", True),
                ("company_id", "=", backend.company_id.id),
            ],
            limit=1,
        )

    def _update_picking_delivery_state(self, marketplace_status):
        self.ensure_one()
        delivery_state = self._marketplace_delivery_state_map().get(marketplace_status)
        if not delivery_state:
            return

        pickings = self.odoo_id.picking_ids.filtered(
            lambda p: p.picking_type_code == "outgoing"
        )
        for picking in pickings:
            vals = {"delivery_state": delivery_state}
            if marketplace_status in self._marketplace_shipped_statuses():
                vals["date_shipped"] = fields.Date.today()
            if marketplace_status in self._marketplace_delivered_statuses():
                vals["date_delivered"] = fields.Datetime.now()
            picking.write(vals)

    def _get_posted_customer_invoice(self):
        self.ensure_one()
        return self.odoo_id.invoice_ids.filtered(
            lambda i: i.state == "posted" and i.move_type == "out_invoice"
        )[:1]
