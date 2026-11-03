from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.delivery_fedex.models.delivery_carrier import DeliveryCarrier

MONDAY = date(2026, 11, 2)


def _rate_reply(delivery_date=None, commit_date=None):
    """A FedEx rate reply trimmed from a live one (Ankara to Hürth, DE)."""
    detail = {
        "serviceType": "FEDEX_REGIONAL_ECONOMY",
        "ratedShipmentDetails": [
            {
                "rateType": "ACCOUNT",
                "totalNetChargeWithDutiesAndTaxes": 26.51,
                "currency": "EUR",
            }
        ],
    }
    if delivery_date:
        detail["operationalDetail"] = {"deliveryDate": delivery_date}
    if commit_date:
        detail["commit"] = {"dateDetail": {"dayFormat": commit_date}}
    return {"output": {"rateReplyDetails": [detail]}}


class FakeRecordSet(list):
    """The recordset methods a customs builder calls, on plain test objects."""

    def filtered(self, predicate):
        return FakeRecordSet(item for item in self if predicate(item))

    def mapped(self, field_name):
        return [getattr(item, field_name) for item in self]


@tagged("post_install", "-at_install")
class TestFedExSaleCustoms(TransactionCase):
    def _product(self, name, category):
        return self.env["product.product"].create(
            {
                "name": name,
                "categ_id": category.id,
                "type": "consu",
                "barcode": f"fedex-customs-test-{name}",
            }
        )

    def _line(self, product, quantity, price, **values):
        return {
            "name": product.name,
            "product_id": product.id,
            "product_uom_qty": quantity,
            "price_unit": price,
            "tax_id": [(6, 0, [])],
            **values,
        }

    def test_commodities_come_from_the_goods_on_the_order(self):
        hs_code = self.env["hs.code"].create(
            {"local_code": "39269097", "description": "Plastic enclosures"}
        )
        with_hs = self.env["product.category"].create(
            {"name": "Enclosures", "hs_code_id": hs_code.id}
        )
        without_hs = self.env["product.category"].create({"name": "Custom"})
        enclosure = self._product("Enclosure", with_hs)
        sample = self._product("Sample", with_hs)
        custom = self._product("Custom part", without_hs)
        delivery = self._product("Shipping", without_hs)
        order = self.env["sale.order"].create(
            {
                "partner_id": self.env["res.partner"].create({"name": "Buyer"}).id,
                "order_line": [
                    (0, 0, self._line(enclosure, 2, 10.0)),
                    (0, 0, self._line(sample, 1, 0.0)),
                    (0, 0, self._line(custom, 1, 5.0)),
                    (0, 0, self._line(delivery, 1, 30.0, is_delivery=True)),
                    (0, 0, {"name": "Note", "display_type": "line_note"}),
                ],
            }
        )
        carrier = self.env["delivery.carrier"].new(
            {"fedex_customs_payment_type": "RECIPIENT"}
        )

        customs = carrier._prepare_fedex_sale_customs_data(order, 9.0)

        # FedEx answers RATE.PAYMENTTYPE.NOTALLOWED to a RECIPIENT payment.
        self.assertNotIn("dutiesPayment", customs)
        commodities = {entry["name"]: entry for entry in customs["commodities"]}
        self.assertEqual(set(commodities), {"Enclosure", "Sample", "Custom part"})
        self.assertEqual(commodities["Enclosure"]["description"], "Plastic enclosures")
        self.assertEqual(commodities["Enclosure"]["harmonizedCode"], hs_code.hs_code)
        self.assertEqual(commodities["Enclosure"]["customsValue"]["amount"], 20.0)
        self.assertEqual(commodities["Enclosure"]["unitPrice"]["amount"], 10.0)
        self.assertEqual(commodities["Enclosure"]["weight"]["value"], 3.0)
        # A free line still needs a value.
        self.assertEqual(commodities["Sample"]["customsValue"]["amount"], 1.0)
        # No HS code anywhere: the name describes it and no false code is sent.
        self.assertEqual(commodities["Custom part"]["description"], "Custom part")
        self.assertNotIn("harmonizedCode", commodities["Custom part"])

    def test_order_without_goods_has_no_commodities(self):
        order = self.env["sale.order"].create(
            {"partner_id": self.env["res.partner"].create({"name": "Buyer"}).id}
        )
        carrier = self.env["delivery.carrier"].new({})

        customs = carrier._prepare_fedex_sale_customs_data(order, 9.0)

        self.assertEqual(customs["commodities"], [])

    def test_sale_commodities_are_split_above_9999_units(self):
        hs_code = self.env["hs.code"].create(
            {"local_code": "39269097", "description": "Plastic enclosures"}
        )
        category = self.env["product.category"].create(
            {"name": "Enclosures", "hs_code_id": hs_code.id}
        )
        product = self._product("Enclosure", category)
        order = self.env["sale.order"].create(
            {
                "partner_id": self.env["res.partner"].create({"name": "Buyer"}).id,
                "order_line": [(0, 0, self._line(product, 25000, 1.0))],
            }
        )
        carrier = self.env["delivery.carrier"].new({})

        commodities = carrier._prepare_fedex_sale_customs_data(order, 30.0)[
            "commodities"
        ]

        self.assertEqual(
            [commodity["quantity"] for commodity in commodities],
            [9999, 9999, 5002],
        )
        self.assertAlmostEqual(
            sum(commodity["customsValue"]["amount"] for commodity in commodities),
            25000.0,
        )
        self.assertAlmostEqual(
            sum(commodity["weight"]["value"] for commodity in commodities),
            30.0,
        )
        for commodity in commodities:
            self.assertEqual(commodity["unitPrice"]["amount"], 1.0)
            self.assertEqual(commodity["name"], "Enclosure")
            self.assertEqual(commodity["harmonizedCode"], hs_code.hs_code)

    def test_commodity_at_the_9999_unit_limit_is_not_split(self):
        hs_code = self.env["hs.code"].create({"local_code": "39269097"})
        category = self.env["product.category"].create(
            {"name": "Enclosures", "hs_code_id": hs_code.id}
        )
        product = self._product("Enclosure", category)
        carrier = self.env["delivery.carrier"].new({})

        commodity = carrier._prepare_fedex_commodities_entry(
            product, 9999, 9999.0, "EUR", 10.0
        )

        self.assertEqual(carrier._split_fedex_commodity(commodity), [commodity])

    def test_shipment_commodities_are_split_above_9999_units(self):
        hs_code = self.env["hs.code"].create({"local_code": "39269097"})
        category = self.env["product.category"].create(
            {"name": "Enclosures", "hs_code_id": hs_code.id}
        )
        product = self._product("Enclosure", category)
        product.default_code = "ENCL-1"
        line = SimpleNamespace(
            product_id=product, quantity=25000, price_subtotal=25000.0
        )
        invoice = SimpleNamespace(
            state="posted", invoice_line_ids=FakeRecordSet([line])
        )
        sale = SimpleNamespace(
            fedex_shipment_purpose="SOLD",
            currency_id=SimpleNamespace(name="EUR"),
        )
        picking = SimpleNamespace(
            location_id=SimpleNamespace(warehouse_id=None),
            partner_id=self.env["res.partner"].create({"name": "Buyer"}),
            sale_id=sale,
            invoice_ids=FakeRecordSet([invoice]),
        )
        carrier = self.env["delivery.carrier"].new(
            {"fedex_customs_payment_type": "RECIPIENT"}
        )

        customs = carrier._prepare_fedex_customs_data(picking, 30.0)

        self.assertEqual(
            [commodity["quantity"] for commodity in customs["commodities"]],
            [9999, 9999, 5002],
        )
        self.assertAlmostEqual(
            sum(
                commodity["customsValue"]["amount"]
                for commodity in customs["commodities"]
            ),
            25000.0,
        )
        self.assertAlmostEqual(
            sum(commodity["weight"]["value"] for commodity in customs["commodities"]),
            30.0,
        )


class TestFedExRate(TransactionCase):
    def test_sale_rate_data_sends_customs_with_transit_times(self):
        carrier = SimpleNamespace(
            _prepare_fedex_base_rate_data=lambda *_args: {"requestedShipment": {}},
            _prepare_fedex_dummy_packages=lambda _order: [
                {"weight": {"units": "KG", "value": 2.0}},
                {"weight": {"units": "KG", "value": 3.0}},
            ],
            _prepare_fedex_sale_customs_data=lambda _order, weight: {"weight": weight},
        )

        data = DeliveryCarrier._prepare_fedex_sale_rate_data(
            carrier, SimpleNamespace(warehouse_id=None, partner_id=None)
        )

        self.assertEqual(
            data["rateRequestControlParameters"], {"returnTransitTimes": True}
        )
        self.assertEqual(
            data["requestedShipment"]["customsClearanceDetail"], {"weight": 5.0}
        )

    def test_transit_days_count_business_days_after_ship_date(self):
        transit_days = self.env["delivery.carrier"]._fedex_transit_days
        # Regional Economy and International Priority replies from 2 Nov 2026.
        self.assertEqual(transit_days(_rate_reply("2026-11-10T18:00:00"), MONDAY), 6)
        self.assertEqual(transit_days(_rate_reply("2026-11-03T18:00:00"), MONDAY), 1)
        # Only the commit date: same answer.
        reply = _rate_reply(commit_date="2026-11-10T18:00:00")
        self.assertEqual(transit_days(reply, MONDAY), 6)
        # Friday to Monday skips the weekend.
        friday = date(2026, 11, 6)
        self.assertEqual(transit_days(_rate_reply("2026-11-09T18:00:00"), friday), 1)
        # No date, or no day after the ship date: unknown.
        self.assertIsNone(transit_days(_rate_reply(), MONDAY))
        self.assertIsNone(transit_days(_rate_reply("2026-11-02T18:00:00"), MONDAY))

    @patch("odoo.addons.delivery_fedex.models.delivery_carrier.FedExRequest")
    def test_sale_rate_returns_transit_days(self, fedex_request):
        fedex_request.return_value.get_rates.return_value = _rate_reply(
            "2026-11-10T18:00:00"
        )
        carriers = self.env["delivery.carrier"]
        carrier = SimpleNamespace(
            fedex_service_type="FEDEX_REGIONAL_ECONOMY",
            fedex_client_id="id",
            fedex_client_secret="secret",
            prod_environment=False,
            _prepare_fedex_sale_rate_data=lambda _order: {
                "requestedShipment": {
                    "shipDateStamp": "2026-11-02",
                    "requestedPackageLineItems": [
                        {"weight": {"units": "KG", "value": 2.0}}
                    ],
                }
            },
            _fedex_transit_days=carriers._fedex_transit_days,
            _format_fedex_rate_data=carriers._format_fedex_rate_data,
        )
        order = SimpleNamespace(currency_id=SimpleNamespace(name="EUR"))

        result = DeliveryCarrier.fedex_rate_shipment(carrier, order)

        self.assertEqual(result["price"], 26.51)
        self.assertEqual(result["transit_days"], 6)

    @patch("odoo.addons.delivery_fedex.models.delivery_carrier.FedExRequest")
    def test_freight_rate_rejects_package_below_minimum_weight(self, fedex_request):
        carrier = SimpleNamespace(
            fedex_service_type="FEDEX_REGIONAL_ECONOMY_FREIGHT",
            _prepare_fedex_sale_rate_data=lambda _order: {
                "requestedShipment": {
                    "requestedPackageLineItems": [
                        {"weight": {"units": "KG", "value": 6.397}}
                    ]
                }
            },
        )

        result = DeliveryCarrier.fedex_rate_shipment(carrier, SimpleNamespace())

        fedex_request.assert_not_called()
        self.assertFalse(result["success"])
        self.assertEqual(result["price"], 0.0)
        self.assertIn("68.01 kg", result["error_message"])
        self.assertIn("6.40 kg", result["error_message"])


@tagged("post_install", "-at_install")
class TestFedExAddress(TransactionCase):
    def _address(self, **values):
        partner = self.env["res.partner"].create(
            dict(name="Buyer", country_id=self.env.ref("base.it").id, **values)
        )
        return self.env["delivery.carrier"].new({})._prepare_fedex_address(partner)

    def test_postal_code_is_trimmed(self):
        # FedEx answers DESTINATION.POSTALCODE.MISSING.ORINVALID to "12345 ".
        address = self._address(zip="12345 ", city="Milan")

        self.assertEqual(address["postalCode"], "12345")

    def test_missing_postal_code_is_sent_as_an_empty_string(self):
        self.assertEqual(self._address()["postalCode"], "")
