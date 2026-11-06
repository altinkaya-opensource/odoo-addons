# Copyright 2026 Altinkaya Enclosures
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestDummyPackages(TransactionCase):
    def _package_weights(self, deci, remainder_percent):
        carrier = self.env["delivery.carrier"].new(
            {
                "name": "Dummy Package Carrier",
                "delivery_type": "fixed",
                "dummy_pallet_threshold": 150.0,
                "dummy_package_weight": 30.0,
                "dummy_remainder_threshold_percent": remainder_percent,
                "factor_a": 1.0,
                "factor_b": 0.01,
            }
        )
        return [pack["weight"] for pack in carrier._generate_dummy_packages(deci)]

    def test_remainder_threshold_is_a_percent(self):
        # 50% of a 30 kg package is 15 kg.
        self.assertEqual(self._package_weights(46.0, 50.0), [30.0, 16.0])
        self.assertEqual(self._package_weights(44.0, 50.0), [30.0])

    def test_zero_threshold_keeps_every_remainder(self):
        self.assertEqual(self._package_weights(31.0, 0.0), [30.0, 1.0])

    def test_small_order_gets_one_package(self):
        self.assertEqual(self._package_weights(10.0, 50.0), [10.0])
