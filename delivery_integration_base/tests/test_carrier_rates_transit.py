# Copyright 2026 Altinkaya Enclosures
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from unittest.mock import patch

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestCarrierRatesTransit(TransactionCase):
    def test_rates_table_shows_carrier_transit_days(self):
        germany = self.env.ref("base.de")
        partner = self.env["res.partner"].create(
            {
                "name": "Rates Table Buyer",
                "street": "Industriestr. 1",
                "city": "Hürth",
                "zip": "50354",
                "country_id": germany.id,
            }
        )
        delivery_product = self.env["product.product"].create(
            {"name": "Rates table delivery", "type": "service"}
        )
        carriers = self.env["delivery.carrier"].create(
            [
                {
                    "name": name,
                    "delivery_type": "fixed",
                    "product_id": delivery_product.id,
                    "currency_id": self.env.company.currency_id.id,
                    "show_in_price_table": True,
                    "country_ids": [(6, 0, germany.ids)],
                }
                for name in ("Transit Express", "Transit Unknown")
            ]
        )
        order = self.env["sale.order"].create({"partner_id": partner.id})
        # Create everything before new(): a create can clear the cache that
        # holds an unsaved record's values.
        wizard = self.env["choose.delivery.carrier"].new({"order_id": order.id})

        def fake_rate_shipment(carrier, _order):
            # Only a caller that asks for the estimate gets it.
            asked = carrier.env.context.get("delivery_transit_days")
            express = carrier.name == "Transit Express"
            return {
                "success": True,
                "price": 25.0,
                "transit_days": 3 if asked and express else None,
            }

        with patch.object(
            type(self.env["delivery.carrier"]),
            "rate_shipment",
            autospec=True,
            side_effect=fake_rate_shipment,
        ):
            wizard.default_get(["carrier_prices"])

        rows = {line.carrier_id: line for line in wizard.carrier_prices}
        self.assertEqual(rows[carriers[0]].transit_days, 3)
        self.assertEqual(rows[carriers[1]].transit_days, 0)  # shown empty
        self.assertEqual(rows[carriers[0]].price, 25.0)
