# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from .common import TrendyolTestCase


class TestTrendyolSettlement(TrendyolTestCase):
    def _create_settlement_row(self, order, settlement_id, commission_amount):
        return self.env["trendyol.settlement"].create(
            {
                "backend_id": self.backend.id,
                "trendyol_settlement_id": settlement_id,
                "transaction_type": "sale",
                "order_number": order.trendyol_order_number,
                "shipment_package_id": order.trendyol_package_id,
                "payment_order_id": "PAYOUT-1",
                "trendyol_order_id": order.id,
                "commission_amount": commission_amount,
            }
        )

    def _prepare_payout_order(self):
        """Return a Trendyol order with a posted invoice ready for payout."""
        journal = self.env["account.journal"].search(
            [
                ("company_id", "=", self.env.company.id),
                ("type", "=", "bank"),
                (
                    "currency_id",
                    "in",
                    [False, self.env.company.currency_id.id],
                ),
            ],
            limit=1,
        )
        payment_method_lines = (
            journal.inbound_payment_method_line_ids
            | journal.outbound_payment_method_line_ids
        )
        payment_method_lines.payment_account_id = journal.default_account_id
        trendyol_partner = self.env["res.partner"].create(
            {"name": "Trendyol Settlement Partner"}
        )
        self.backend.write(
            {
                "settlement_journal_id": journal.id,
                "trendyol_partner_id": trendyol_partner.id,
            }
        )
        customer = self.env["res.partner"].search(
            [
                ("state_id", "!=", False),
                ("country_id", "!=", False),
                ("street", "!=", False),
                ("einvoice_registered_user", "=", False),
            ],
            limit=1,
        )
        if not customer:
            self.skipTest("A complete customer address is required for invoice posting")
        product = self.env["product.product"].create(
            {
                "name": "Settlement Product",
                "type": "service",
                "detailed_type": "service",
                "invoice_policy": "order",
            }
        )
        sale = self.env["sale.order"].create(
            {
                "partner_id": customer.id,
                "warehouse_id": self.backend.warehouse_ids[:1].id,
                "pricelist_id": self.backend.pricelist_id.id,
                "order_line": [
                    (
                        0,
                        0,
                        {
                            "product_id": product.id,
                            "product_uom_qty": 1,
                            "price_unit": 100,
                        },
                    )
                ],
            }
        )
        sale_line = sale.order_line
        invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": customer.id,
                "invoice_line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": product.id,
                            "quantity": 1,
                            "price_unit": 100,
                            "sale_line_ids": [(6, 0, sale_line.ids)],
                        },
                    )
                ],
            }
        )
        invoice.action_post()
        order = self.env["trendyol.order"].create(
            {
                "odoo_id": sale.id,
                "backend_id": self.backend.id,
                "trendyol_order_number": "SETTLEMENT-ORDER",
                "trendyol_package_id": "SETTLEMENT-PACKAGE",
            }
        )
        return order, invoice

    def test_package_rows_are_reconciled_with_one_payment(self):
        order, invoice = self._prepare_payout_order()
        settlements = self._create_settlement_row(
            order, "SETTLEMENT-1", 10
        ) | self._create_settlement_row(order, "SETTLEMENT-2", 5)

        settlements[0]._reconcile()

        self.assertEqual(settlements.mapped("state"), ["reconciled", "reconciled"])
        self.assertEqual(len(settlements.odoo_payment_id), 1)
        self.assertEqual(len(settlements.commission_payment_id), 1)
        self.assertEqual(settlements.commission_payment_id.amount, 15)
        self.assertEqual(settlements.odoo_invoice_id, invoice)

    def test_late_row_is_flagged_without_touching_reconciled_rows(self):
        order, _invoice = self._prepare_payout_order()
        settlements = self._create_settlement_row(
            order, "SETTLEMENT-1", 10
        ) | self._create_settlement_row(order, "SETTLEMENT-2", 5)
        settlements[0]._reconcile()
        payment = settlements.odoo_payment_id
        commission_payment = settlements.commission_payment_id

        late_row = self._create_settlement_row(order, "SETTLEMENT-3", 7)
        late_row._reconcile()

        self.assertEqual(settlements.mapped("state"), ["reconciled", "reconciled"])
        self.assertEqual(settlements.odoo_payment_id, payment)
        self.assertEqual(settlements.commission_payment_id, commission_payment)
        self.assertEqual(commission_payment.state, "posted")
        self.assertEqual(late_row.state, "error")
        self.assertTrue(late_row.manual_review_required)
        self.assertFalse(late_row.odoo_payment_id)

    def test_rows_without_package_and_order_keys_are_not_grouped(self):
        settlements = self.env["trendyol.settlement"].create(
            [
                {
                    "backend_id": self.backend.id,
                    "trendyol_settlement_id": "KEYLESS-1",
                    "transaction_type": "sale",
                },
                {
                    "backend_id": self.backend.id,
                    "trendyol_settlement_id": "KEYLESS-2",
                    "transaction_type": "sale",
                },
            ]
        )

        self.assertEqual(
            settlements[0]._get_reconciliation_group(),
            settlements[0],
        )

    def test_manual_reconcile_reports_failure_as_failure(self):
        settlement = self.env["trendyol.settlement"].create(
            {
                "backend_id": self.backend.id,
                "trendyol_settlement_id": "NO-JOURNAL",
                "transaction_type": "sale",
            }
        )

        action = settlement.action_reconcile()

        self.assertEqual(settlement.state, "error")
        self.assertEqual(action["params"]["type"], "danger")
