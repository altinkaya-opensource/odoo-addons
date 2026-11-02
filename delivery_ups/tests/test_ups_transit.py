from types import SimpleNamespace
from unittest.mock import Mock, patch

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.delivery_ups.models.delivery_carrier import DeliveryCarrier

# Trimmed from a live Rating "Ratetimeintransit" reply, Ankara to Hürth (DE),
# 2 Nov 2026.
UPS_TRANSIT_RESPONSE = {
    "RateResponse": {
        "RatedShipment": {
            "TimeInTransit": {
                "PickupDate": "20261103",
                "ServiceSummary": {
                    "Service": {"Description": "UPS Express Saver"},
                    "EstimatedArrival": {
                        "Arrival": {"Date": "20261106", "Time": "233000"},
                        "BusinessDaysInTransit": "3",
                        "TotalTransitDays": "3",
                    },
                },
            }
        }
    }
}


@tagged("post_install", "-at_install")
class TestUPSTransit(TransactionCase):
    def _rate_carrier(self, context):
        return SimpleNamespace(
            base_on_rule_rate_shipment=lambda _order: {"success": True, "price": 12.5},
            env=SimpleNamespace(context=context),
            _ups_transit_days=Mock(return_value=3),
        )

    def _transit_carrier(self):
        return SimpleNamespace(
            prod_environment=False,
            ups_client_id="id",
            ups_client_secret="secret",
            ups_account_number="A1",
            _prepare_ups_transit_data=lambda _order: {},
        )

    def test_rate_asks_transit_only_for_the_storefront(self):
        carrier = self._rate_carrier({})
        result = DeliveryCarrier.ups_rate_shipment(carrier, SimpleNamespace())
        carrier._ups_transit_days.assert_not_called()
        self.assertEqual(result, {"success": True, "price": 12.5})

        carrier = self._rate_carrier({"delivery_transit_days": True})
        result = DeliveryCarrier.ups_rate_shipment(carrier, SimpleNamespace())
        self.assertEqual(result, {"success": True, "price": 12.5, "transit_days": 3})

    @patch("odoo.addons.delivery_ups.models.delivery_carrier.UPSRequest")
    def test_transit_days_from_rating(self, ups_request):
        ups_request.return_value.get_transit_time.return_value = UPS_TRANSIT_RESPONSE

        days = DeliveryCarrier._ups_transit_days(
            self._transit_carrier(), SimpleNamespace(name="SO1")
        )

        self.assertEqual(days, 3)

    @patch("odoo.addons.delivery_ups.models.delivery_carrier.UPSRequest")
    def test_transit_days_from_list_reply(self, ups_request):
        # Live replies for a UK cart came back as a one-item list.
        rated = UPS_TRANSIT_RESPONSE["RateResponse"]["RatedShipment"]
        ups_request.return_value.get_transit_time.return_value = {
            "RateResponse": {"RatedShipment": [rated]}
        }

        days = DeliveryCarrier._ups_transit_days(
            self._transit_carrier(), SimpleNamespace(name="SO1")
        )

        self.assertEqual(days, 3)

    @patch("odoo.addons.delivery_ups.models.delivery_carrier.UPSRequest")
    def test_transit_error_returns_none(self, ups_request):
        ups_request.return_value.get_transit_time.side_effect = UserError(
            "UPS Error: [111546] Invalid Weight."
        )

        days = DeliveryCarrier._ups_transit_days(
            self._transit_carrier(), SimpleNamespace(name="SO1")
        )

        self.assertIsNone(days)

    def test_transit_request_payload(self):
        # Create records before new(): a create can clear the cache that
        # holds an unsaved record's values.
        recipient = self.env["res.partner"].create(
            {
                "name": "Hürth Customer",
                "street": "Industriestr. 1",
                "city": "Hürth",
                "zip": "50354",
                "country_id": self.env.ref("base.de").id,
            }
        )
        carrier = self.env["delivery.carrier"].new(
            {
                "name": "UPS Saver",
                "delivery_type": "ups",
                "ups_service_type": "65",
                "ups_account_number": "A1",
                "dummy_pallet_threshold": 100.0,
                "dummy_package_weight": 30.0,
                "factor_a": 1.0,
                "factor_b": 0.0,
            }
        )
        company = self.env.company
        order = SimpleNamespace(
            name="SOTEST",
            warehouse_id=SimpleNamespace(partner_id=company.partner_id),
            partner_shipping_id=recipient,
            company_id=company,
            currency_id=company.currency_id,
            amount_untaxed=2000.0,
            sale_deci=2.0,
        )

        shipment = carrier._prepare_ups_transit_data(order)["RateRequest"]["Shipment"]

        self.assertEqual(shipment["ShipTo"]["Address"]["CountryCode"], "DE")
        self.assertEqual(shipment["Shipper"]["ShipperNumber"], "A1")
        self.assertEqual(shipment["Service"]["Code"], "65")
        self.assertEqual(shipment["DeliveryTimeInformation"]["PackageBillType"], "03")
        self.assertEqual(
            shipment["InvoiceLineTotal"],
            {"CurrencyCode": company.currency_id.name, "MonetaryValue": "2000"},
        )
        package = shipment["Package"][0]
        self.assertEqual(package["PackagingType"]["Code"], "02")
        # UPS answers 111546 "Invalid Weight" without these descriptions.
        self.assertEqual(
            package["PackageWeight"]["UnitOfMeasurement"]["Description"], "Kilograms"
        )
        self.assertEqual(
            shipment["ShipmentTotalWeight"]["Weight"],
            package["PackageWeight"]["Weight"],
        )
