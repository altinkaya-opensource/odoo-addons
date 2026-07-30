from odoo.tests import tagged
from odoo.tests.common import TransactionCase


# Pricing goes through altinkaya_pricelist's _compute_base_price override, the
# same reason test_set_price.py runs post_install: at_install tests would run
# before that module patches the registry.
@tagged("post_install", "-at_install")
class TestAmountUntaxedUsd(TransactionCase):
    """The USD total has to survive an order created with its lines in one
    transaction, which is what the marketplace connectors do."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # A date no imported rate can reach, so the "last rate on or before
        # the order date" lookup is deterministic whatever the database holds.
        cls.rate_date = "2099-06-15"
        Rate = cls.env["res.currency.rate"]
        Rate.create(
            {
                "currency_id": cls.env.ref("base.USD").id,
                "name": cls.rate_date,
                "rate": 0.02,
            }
        )
        Rate.create(
            {
                "currency_id": cls.env.ref("base.EUR").id,
                "name": cls.rate_date,
                "rate": 0.016,
            }
        )

        cls.partner = cls.env["res.partner"].create({"name": "USD compute customer"})
        cls.product = cls.env["product.product"].create(
            {
                "name": "USD compute product",
                "type": "consu",
                "detailed_type": "consu",
                "list_price": 100.0,
            }
        )
        cls.pricelists = {
            code: cls.env["product.pricelist"].create(
                {
                    "name": f"USD compute {code}",
                    "currency_id": cls.env.ref(f"base.{code}").id,
                }
            )
            for code in ("TRY", "USD", "EUR")
        }

    def _stored_usd(self, currency_code, date_order):
        """Create an order and its line in one transaction, connector style."""
        order = self.env["sale.order"].create(
            {
                "partner_id": self.partner.id,
                "pricelist_id": self.pricelists[currency_code].id,
                "date_order": date_order,
            }
        )
        self.env["sale.order.line"].create(
            {
                "order_id": order.id,
                "product_id": self.product.id,
                "product_uom_qty": 1,
                "price_unit": 1000.0,
            }
        )
        self.env.flush_all()
        order.invalidate_recordset()
        self.assertEqual(order.amount_untaxed, 1000.0)
        return order.amount_untaxed_usd

    def test_order_and_line_in_one_transaction_converts_amount(self):
        stored = self._stored_usd("TRY", f"{self.rate_date} 10:00:00")
        self.assertAlmostEqual(stored, 20.0, places=2)

    def test_usd_pricelist_order_is_not_converted(self):
        stored = self._stored_usd("USD", f"{self.rate_date} 10:00:00")
        self.assertAlmostEqual(stored, 1000.0, places=2)

    def test_eur_pricelist_order_converts_through_usd(self):
        stored = self._stored_usd("EUR", f"{self.rate_date} 10:00:00")
        self.assertAlmostEqual(stored, 1250.0, places=2)

    def test_order_dated_before_any_rate_stores_zero(self):
        stored = self._stored_usd("TRY", "1990-05-05 10:00:00")
        self.assertEqual(stored, 0.0)
