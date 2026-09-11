# Copyright 2026 Altinkaya Enclosures
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import Command
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestIyzicoPaymentConfirmation(TransactionCase):
    """Exercise the confirmation path shared by direct and 3DS payments."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.provider = cls.env.ref("payment_iyzico_altinkaya.payment_provider_iyzico")
        cls.partner = cls.env["res.partner"].create({"name": "Card Payment Customer"})
        if "risk_sale_order_include" in cls.partner._fields:
            cls.partner.write({"credit_limit": 0, "risk_sale_order_include": True})
        if "exception.rule" in cls.env:
            cls.env["exception.rule"].search(
                [("model", "in", ["sale.order", "sale.order.line"])]
            ).active = False
        cls.product = cls.env["product.product"].create(
            {"name": "Card Payment Service", "type": "service", "taxes_id": False}
        )

    def setUp(self):
        super().setUp()
        self.order = self.env["sale.order"].create(
            {
                "partner_id": self.partner.id,
                "order_line": [
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "product_uom_qty": 1,
                            "price_unit": 100,
                            "tax_id": [Command.clear()],
                        }
                    )
                ],
            }
        )
        self.tx = self.env["payment.transaction"].create(
            {
                "provider_id": self.provider.id,
                "reference": f"IYZICO-CONFIRM-{self.order.id}",
                "amount": self.order.amount_total,
                "currency_id": self.order.currency_id.id,
                "partner_id": self.partner.id,
                "sale_order_ids": [Command.set(self.order.ids)],
                "operation": "online_direct",
            }
        )

    def _finalize_success(self):
        self.tx._iyzico_finalize_payment(
            "success",
            {"currency": self.tx.currency_id.name, "paidPrice": self.tx.amount},
        )
        self.assertEqual(self.tx.state, "done")

    def test_paid_order_confirms_without_customer_credit(self):
        self._finalize_success()
        self.assertIn(self.order.state, ("sale", "done"))

    def test_failed_payment_does_not_confirm(self):
        self.tx._iyzico_finalize_payment("error", "Payment declined")
        self.assertEqual(self.tx.state, "error")
        self.assertEqual(self.order.state, "draft")

    def test_partial_payment_does_not_confirm(self):
        self.tx.amount /= 2
        self._finalize_success()
        self.assertEqual(self.order.state, "draft")

    def test_changed_order_total_does_not_confirm(self):
        self.order.order_line.product_uom_qty = 2
        self._finalize_success()
        self.assertEqual(self.order.state, "draft")

    def test_paid_order_still_checks_sale_exceptions(self):
        if "exception.rule" not in self.env:
            self.skipTest("sale_exception is not installed")
        rule = self.env["exception.rule"].create(
            {
                "name": "Payment must not skip this exception",
                "model": "sale.order",
                "exception_type": "by_py_code",
                "code": "failed = True",
            }
        )
        self._finalize_success()
        self.assertNotIn(self.order.state, ("sale", "done"))
        self.assertIn(rule, self.order.exception_ids)
        self.assertFalse(self.order.ignore_exception)
