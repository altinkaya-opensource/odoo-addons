# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from datetime import datetime

from odoo import fields
from odoo.tools import mute_logger

from .common import HepsiburadaCommon


class TestHepsiburadaSettlement(HepsiburadaCommon):
    def test_import_settlement_parses_iso_dates(self):
        settlement = self.env["hepsiburada.settlement"]._import_settlement(
            self.backend,
            {
                "id": "iso-dates",
                "recordDate": "2026-09-01T00:00:00",
                "paymentDate": "2026-09-02T10:30:00.123",
            },
        )

        self.assertEqual(settlement.transaction_date, datetime(2026, 9, 1))
        self.assertEqual(
            settlement.payment_date, datetime(2026, 9, 2, 10, 30, 0, 123000)
        )

    def test_import_settlement_updates_dates_in_utc(self):
        settlement_model = self.env["hepsiburada.settlement"]
        settlement = settlement_model._import_settlement(
            self.backend, {"id": "updated-dates"}
        )

        updated = settlement_model._import_settlement(
            self.backend,
            {
                "id": "updated-dates",
                "recordDate": "2026-09-01T01:00:00+03:00",
                "paymentDate": "2026-09-02T10:30:00Z",
            },
        )

        self.assertEqual(updated, settlement)
        self.assertEqual(updated.transaction_date, datetime(2026, 8, 31, 22))
        self.assertEqual(updated.payment_date, datetime(2026, 9, 2, 10, 30))

    def test_import_settlement_rejects_invalid_dates(self):
        for field_name in ("recordDate", "paymentDate"):
            with (
                self.subTest(field_name=field_name),
                mute_logger(
                    "odoo.addons.hepsiburada_integration.models.hepsiburada_settlement"
                ),
                self.assertRaises(ValueError),
                self.env.cr.savepoint(),
            ):
                self.env["hepsiburada.settlement"]._import_settlement(
                    self.backend,
                    {"id": f"invalid-{field_name}", field_name: "invalid-date"},
                )

    def test_import_settlement_extracts_nested_amount(self):
        settlement = self.env["hepsiburada.settlement"]._import_settlement(
            self.backend,
            {
                "id": "transaction-1",
                "transactionType": "Commission",
                "amount": {"value": -408.0, "currencyCode": "949"},
                "status": "WillBePaid",
            },
        )

        self.assertEqual(settlement.amount, -408.0)
        self.assertEqual(settlement.currency_code, "949")
        self.assertFalse(settlement.transaction_date)
        self.assertFalse(settlement.payment_date)

    def test_unknown_status_is_not_reconciled(self):
        settlement = self.env["hepsiburada.settlement"].create(
            {
                "backend_id": self.backend.id,
                "hb_transaction_id": "will-be-paid",
                "transaction_type": "sale",
                "amount": 100,
                "currency_code": "949",
                "payment_status": "Unknown",
            }
        )

        self.assertFalse(settlement._reconcile())
        self.assertEqual(settlement.state, "error")
        self.assertFalse(settlement.odoo_payment_id)

    def test_unsupported_rows_stay_imported_after_a_sync(self):
        settlements = self.env["hepsiburada.settlement"].create(
            [
                {
                    "backend_id": self.backend.id,
                    "hb_transaction_id": "commission-row",
                    "transaction_type": "expense",
                    "amount": -40,
                    "currency_code": "949",
                    "payment_status": "Paid",
                    "order_number": "ORDER-UNRECONCILED",
                },
                {
                    "backend_id": self.backend.id,
                    "hb_transaction_id": "will-be-paid-row",
                    "transaction_type": "sale",
                    "amount": 100,
                    "currency_code": "949",
                    "payment_status": "Unknown",
                    "order_number": "ORDER-UNRECONCILED",
                },
            ]
        )

        self.backend._reconcile_settlements(settlements)

        self.assertEqual(set(settlements.mapped("state")), {"imported"})
        self.assertFalse(any(settlements.mapped("error_message")))

    def test_paid_rows_are_reconciled_as_one_amount_group(self):
        bank_journal = self.env["account.journal"].search(
            [
                ("company_id", "=", self.env.company.id),
                ("type", "=", "bank"),
                "|",
                ("currency_id", "=", False),
                ("currency_id", "=", self.env.company.currency_id.id),
            ],
            limit=1,
        )
        self.assertTrue(bank_journal, "A bank journal is required for this test")
        self.backend.settlement_journal_id = bank_journal
        partner = self.env["res.partner"].create({"name": "HB Customer"})
        sale = self.env["sale.order"].create(
            {
                "partner_id": partner.id,
                "warehouse_id": self.backend.warehouse_ids[:1].id,
                "pricelist_id": self.backend.pricelist_id.id,
            }
        )
        product = self.env["product.product"].create(
            {
                "name": "HB Settlement Product",
                "detailed_type": "product",
                "list_price": 100,
                "taxes_id": [(5, 0, 0)],
            }
        )
        sale_line = self.env["sale.order.line"].create(
            {
                "order_id": sale.id,
                "name": "HB item",
                "product_id": product.id,
                "product_uom": product.uom_id.id,
                "product_uom_qty": 1,
                "price_unit": 100,
            }
        )
        income_account = self.env["account.account"].search(
            [
                ("company_id", "=", self.env.company.id),
                ("account_type", "=", "income"),
                ("deprecated", "=", False),
            ],
            limit=1,
        )
        invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": partner.id,
                "invoice_line_ids": [
                    (
                        0,
                        0,
                        {
                            "name": "HB item",
                            "quantity": 1,
                            "price_unit": 100,
                            "account_id": income_account.id,
                            "tax_ids": [(5, 0, 0)],
                            "sale_line_ids": [(6, 0, sale_line.ids)],
                        },
                    )
                ],
            }
        )
        # The e-invoice module is not a dependency of this addon.
        if "prevent_einvoice_generation" in invoice.journal_id._fields:
            invoice.journal_id.prevent_einvoice_generation = True
        if hasattr(invoice, "_update_einvoice_fields"):
            invoice._update_einvoice_fields()
        self.env["exception.rule"].search(
            [("name", "=", "Paket Bilgisi Eksik")]
        ).active = False
        invoice.action_post()
        self.env["hepsiburada.order"].create(
            {
                "backend_id": self.backend.id,
                "odoo_id": sale.id,
                "hb_order_number": "ORDER-PAID",
                "hb_status": "delivered",
            }
        )
        currency_code = {
            "TRY": "949",
            "USD": "840",
        }.get(invoice.currency_id.name, "")
        settlements = self.env["hepsiburada.settlement"].create(
            [
                {
                    "backend_id": self.backend.id,
                    "hb_transaction_id": "paid-row-1",
                    "transaction_type": "sale",
                    "amount": 40,
                    "currency_code": currency_code,
                    "payment_status": "WillBePaid",
                    "payment_date": False,
                    "order_number": "ORDER-PAID",
                    "package_number": "PACKAGE-PAID",
                },
                {
                    "backend_id": self.backend.id,
                    "hb_transaction_id": "paid-row-2",
                    "transaction_type": "sale",
                    "amount": 60,
                    "currency_code": currency_code,
                    "payment_status": "WillBePaid",
                    "payment_date": False,
                    "order_number": "ORDER-PAID",
                    "package_number": "PACKAGE-PAID",
                },
            ]
        )

        self.assertIn(invoice, sale.invoice_ids)
        result = settlements[0]._reconcile()
        self.assertTrue(result, settlements.mapped("error_message"))

        self.assertEqual(set(settlements.mapped("state")), {"reconciled"})
        self.assertEqual(len(settlements.mapped("odoo_payment_id")), 1)
        self.assertEqual(settlements[0].odoo_payment_id.amount, 100)
        self.assertEqual(invoice.payment_state, "paid")

        payment = settlements.odoo_payment_id
        settlements.write(
            {"payment_status": "Paid", "payment_date": fields.Datetime.now()}
        )
        self.assertTrue(settlements[1]._reconcile())
        self.assertEqual(settlements.odoo_payment_id, payment)
        self.assertFalse(settlements.commission_payment_id)
