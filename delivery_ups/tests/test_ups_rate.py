from types import SimpleNamespace
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase

from odoo.addons.delivery_ups.models.delivery_carrier import DeliveryCarrier


class TestUPSRate(TransactionCase):
    def test_rate_package_uses_rating_contract_and_positive_weight(self):
        carrier = SimpleNamespace(
            ups_packaging_type="02",
            _generate_dummy_packages=lambda _weight: [
                {
                    "weight": 0.0,
                    "dimensions": {"length": 30, "width": 20, "height": 10},
                    "is_pallet": False,
                }
            ],
        )
        order = SimpleNamespace(picking_ids=False, sale_deci=0.0)

        package = DeliveryCarrier._prepare_ups_dummy_packages(carrier, order)[0]

        self.assertEqual(package["PackagingType"], {"Code": "02"})
        self.assertNotIn("Packaging", package)
        self.assertEqual(package["PackageWeight"]["Weight"], "0.1")

    @patch(
        "odoo.addons.delivery_ups.models.delivery_carrier.UPSRequest",
        side_effect=UserError("UPS Error: [111212] Invalid package type"),
    )
    def test_rate_error_is_returned_to_caller(self, _ups_request):
        carrier = SimpleNamespace(
            prod_environment=True,
            ups_client_id="client",
            ups_client_secret="secret",
            ups_account_number="account",
        )

        result = DeliveryCarrier.ups_rate_shipment(carrier, SimpleNamespace())

        self.assertFalse(result["success"])
        self.assertEqual(result["price"], 0.0)
        self.assertIn("[111212]", result["error_message"])
