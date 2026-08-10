from types import SimpleNamespace
from unittest.mock import patch

from odoo.tests.common import TransactionCase

from odoo.addons.delivery_fedex.models.delivery_carrier import DeliveryCarrier


class TestFedExRate(TransactionCase):
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
