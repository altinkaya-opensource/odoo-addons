from types import SimpleNamespace
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.delivery_dhl.models.delivery_carrier import DeliveryCarrier

# Trimmed from a live MyDHL /rates reply, Ankara to Hürth (DE), 2 Nov 2026.
DHL_RATE_RESPONSE = {
    "exchangeRates": [{"baseCurrency": "EUR"}],
    "products": [
        {
            "productCode": "P",
            "totalPrice": [
                {"currencyType": "BILLC", "priceCurrency": "EUR", "price": 79.27}
            ],
            "deliveryCapabilities": {
                "estimatedDeliveryDateAndTime": "2026-11-04T23:59:00",
                "totalTransitDays": 1,
            },
        }
    ],
}


@tagged("post_install", "-at_install")
class TestDHLRate(TransactionCase):
    def _carrier(self):
        return SimpleNamespace(
            dhl_api_key="key",
            dhl_api_secret="secret",
            prod_environment=False,
            _prepare_dhl_sale_rate_data=lambda _order: {},
            _dhl_transit_days=self.env["delivery.carrier"]._dhl_transit_days,
        )

    def test_transit_days_from_delivery_capabilities(self):
        carrier = self.env["delivery.carrier"]
        self.assertEqual(carrier._dhl_transit_days(DHL_RATE_RESPONSE), 1)
        self.assertIsNone(carrier._dhl_transit_days({"products": [{}]}))
        self.assertIsNone(carrier._dhl_transit_days({}))

    @patch("odoo.addons.delivery_dhl.models.delivery_carrier.DHLRequest")
    def test_rate_returns_transit_days(self, dhl_request):
        dhl_request.return_value.get_rate.return_value = DHL_RATE_RESPONSE
        order = SimpleNamespace(currency_id=SimpleNamespace(name="EUR"))

        result = DeliveryCarrier.dhl_rate_shipment(self._carrier(), order)

        self.assertEqual(result["price"], 79.27)
        self.assertEqual(result["transit_days"], 1)
        self.assertFalse(result["api_error"])

    @patch("odoo.addons.delivery_dhl.models.delivery_carrier.DHLRequest")
    def test_failed_rate_has_no_transit_days(self, dhl_request):
        dhl_request.return_value.get_rate.side_effect = Exception("410105")
        order = SimpleNamespace(currency_id=SimpleNamespace(name="EUR"))

        result = DeliveryCarrier.dhl_rate_shipment(self._carrier(), order)

        self.assertEqual(result["price"], 0.0)
        self.assertIsNone(result["transit_days"])
        # The wizard and the storefront still list the carrier.
        self.assertTrue(result["success"])
        self.assertEqual(result["api_error"], "410105")

    def test_dummy_packages_apply_the_dimension_factor_once(self):
        carrier = self.env["delivery.carrier"].new(
            {
                "delivery_type": "dhl",
                "dummy_pallet_threshold": 150.0,
                "dummy_package_weight": 30.0,
                "factor_a": 2.0,
                "factor_b": 0.1,
            }
        )
        order = SimpleNamespace(picking_ids=[])

        with patch.object(type(carrier), "_get_order_deci", return_value=10.0):
            packages = carrier._prepare_dhl_dummy_packages(order)

        # 10 x (2.0 - 0.1 * log10(10)) = 19; factored twice it would be 35.6.
        self.assertEqual([pack["weight"] for pack in packages], [19.0])

    def test_only_a_preview_rates_a_shipped_order(self):
        carrier = self.env["delivery.carrier"].new({"delivery_type": "dhl"})
        order = SimpleNamespace(picking_ids=[object()])

        with patch.object(type(carrier), "_get_order_deci", return_value=10.0):
            with self.assertRaises(UserError):
                carrier._prepare_dhl_dummy_packages(order)
            packages = carrier.with_context(
                delivery_rate_preview=True
            )._prepare_dhl_dummy_packages(order)

        self.assertEqual(len(packages), 1)
