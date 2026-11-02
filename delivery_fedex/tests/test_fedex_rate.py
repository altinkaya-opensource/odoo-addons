from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

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


class TestFedExRate(TransactionCase):
    def test_sale_rate_data_requests_transit_times(self):
        carrier = SimpleNamespace(
            _prepare_fedex_base_rate_data=lambda *_args: {"requestedShipment": {}},
            _prepare_fedex_dummy_packages=lambda _order: [],
        )

        data = DeliveryCarrier._prepare_fedex_sale_rate_data(
            carrier, SimpleNamespace(warehouse_id=None, partner_id=None)
        )

        self.assertEqual(
            data["rateRequestControlParameters"], {"returnTransitTimes": True}
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
