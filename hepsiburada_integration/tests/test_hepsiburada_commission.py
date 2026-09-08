# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from datetime import datetime
from unittest.mock import Mock

from .common import HepsiburadaCommon


class TestHepsiburadaCommission(HepsiburadaCommon):
    def setUp(self):
        super().setUp()
        if "short.url.yourls" in self.env:
            self.patch(
                type(self.env["short.url.yourls"]),
                "shorten_url",
                lambda service, url: url,
            )
        journal = self.env["account.journal"].search(
            [
                ("company_id", "=", self.env.company.id),
                ("type", "=", "bank"),
                ("currency_id", "in", [False, self.env.company.currency_id.id]),
            ],
            limit=1,
        )
        self.assertTrue(journal)
        (
            journal.inbound_payment_method_line_ids
            | journal.outbound_payment_method_line_ids
        ).payment_account_id = journal.default_account_id
        supplier = self.env["res.partner"].create({"name": "HB Commission Supplier"})
        self.backend.write(
            {"settlement_journal_id": journal.id, "hb_partner_id": supplier.id}
        )

    def _payload(
        self,
        key="commission-1",
        number="HB20269999900001",
        amount=-120,
        transaction="Commission",
    ):
        """Model actual nested HB money values, including tax and dot references."""
        return {
            "id": key,
            "transactionType": transaction,
            "invoiceNumber": number,
            "isInvoice": True,
            "isIncome": amount > 0,
            "status": "WillBePaid",
            "amount": {"value": amount, "currencyCode": "949"},
            "netAmount": {"value": amount / 1.2, "currencyCode": "949"},
            "taxAmount": {"value": amount - amount / 1.2, "currencyCode": "949"},
            "orderNumber": "HB-ORDER",
            "invoiceDate": "2026-09-01T00:00:00",
        }

    def _row(self, **values):
        return self.env["hepsiburada.settlement"]._import_settlement(
            self.backend, self._payload(**values)
        )

    def _invoice(
        self,
        number="HB20269999900001",
        amount=240,
        move_type="in_invoice",
        partner=False,
        currency=False,
    ):
        """Post a real accounting document without external e-invoice delivery."""
        account = self.env["account.account"].search(
            [
                ("company_id", "=", self.env.company.id),
                (
                    "account_type",
                    "=",
                    "income" if move_type.startswith("out_") else "expense",
                ),
                ("deprecated", "=", False),
            ],
            limit=1,
        )
        invoice = self.env["account.move"].create(
            {
                "move_type": move_type,
                "partner_id": (partner or self.backend.hb_partner_id).id,
                "invoice_date": "2026-09-01",
                "ref": number,
                "currency_id": (currency or self.env.company.currency_id).id,
                "invoice_line_ids": [
                    (
                        0,
                        0,
                        {
                            "name": "Commission",
                            "account_id": account.id,
                            "quantity": 1,
                            "price_unit": amount,
                            "tax_ids": [(5, 0, 0)],
                        },
                    )
                ],
            }
        )
        if "ignore_exception" in invoice._fields:
            invoice.ignore_exception = True
        if "prevent_einvoice_generation" in invoice.journal_id._fields:
            invoice.journal_id.prevent_einvoice_generation = True
        if hasattr(invoice, "_update_einvoice_fields"):
            invoice._update_einvoice_fields()
        invoice.action_post()
        self.assertEqual(invoice.state, "posted")
        invoice.ref = number
        return invoice

    def test_commission_gross_payment_matches_only_referenced_bill(self):
        unrelated = self._invoice(number="OLDER-BILL", amount=120)
        bill = self._invoice()
        row = self._row()
        self.assertTrue(row._reconcile())
        payment = row.commission_payment_id
        self.assertEqual(payment.amount, 120)
        self.assertEqual(payment.date.isoformat(), "2026-09-01")
        self.assertTrue(payment.is_hepsiburada_commission)
        self.assertEqual(row.commission_invoice_id, bill)
        self.assertEqual(bill.amount_residual, 120)
        self.assertEqual(unrelated.amount_residual, 120)
        self.assertEqual(row.payment_status, "WillBePaid")
        self.assertFalse(row.odoo_payment_id)
        self.assertTrue(row._reconcile())
        self.assertEqual(row.commission_payment_id, payment)
        notes = self.env["mail.message"].search(
            [
                ("model", "=", "account.move"),
                ("res_id", "=", bill.id),
                ("body", "ilike", "HB-ORDER"),
            ]
        )
        self.assertEqual(len(notes), 1)
        self.assertFalse(notes.notification_ids)

    def test_dot_reference_then_late_invoice_reuses_payment(self):
        row = self._row(number=".")
        self.assertFalse(row._reconcile())
        payment = row.commission_payment_id
        self.assertTrue(payment)
        self.assertEqual(row.commission_match_state, "waiting")
        self.assertFalse(row.commission_invoice_number)
        self._row()
        self.backend._reconcile_pending_commissions()
        self.assertEqual(row.commission_match_state, "waiting")
        bill = self._invoice(amount=120)
        self.backend._reconcile_pending_commissions()
        self.assertEqual(row.commission_payment_id, payment)
        self.assertEqual(row.commission_match_state, "matched")
        self.assertEqual(bill.amount_residual, 0)

    def test_independent_rows_with_same_invoice_are_all_cleared(self):
        bill = self._invoice(amount=240)
        rows = self._row(key="first") | self._row(key="second")
        self.backend._reconcile_settlements(rows)
        self.assertEqual(len(rows.commission_payment_id), 2)
        self.assertEqual(set(rows.mapped("commission_match_state")), {"matched"})
        self.assertEqual(bill.amount_residual, 0)
        payments = rows.commission_payment_id
        self.backend._reconcile_settlements(rows)
        self.assertEqual(rows.commission_payment_id, payments)

    def test_commission_refund_uses_supplier_credit_note(self):
        bill = self._invoice(amount=120, move_type="in_refund")
        row = self._row(amount=120, transaction="CommissionRefund")
        self.assertTrue(row._reconcile())
        self.assertEqual(row.commission_payment_id.partner_type, "supplier")
        self.assertEqual(row.commission_payment_id.payment_type, "inbound")
        self.assertEqual(row.commission_invoice_id, bill)
        self.assertEqual(bill.amount_residual, 0)

    def test_commission_invoice_refund_uses_our_customer_invoice(self):
        invoice = self._invoice(amount=120, move_type="out_invoice")
        row = self._row(amount=120, transaction="CommissionInvoiceRefund")
        self.assertTrue(row._reconcile())
        self.assertEqual(row.commission_payment_id.partner_type, "customer")
        self.assertEqual(row.commission_payment_id.payment_type, "inbound")
        self.assertEqual(row.commission_invoice_id, invoice)
        self.assertEqual(invoice.amount_residual, 0)

    def test_invalid_direction_and_unknown_currency_do_not_create_payments(self):
        row = self._row(amount=120)
        self.assertFalse(row._reconcile())
        self.assertFalse(row.commission_payment_id)
        self.assertEqual(row.commission_match_state, "review")
        row = self._row(key="bad-currency")
        row.currency_code = "999"
        self.assertFalse(row._reconcile())
        self.assertFalse(row.commission_payment_id)

    def test_missing_supplier_does_not_mark_commission_reconciled(self):
        row = self._row()
        self.backend.hb_partner_id = False
        self.assertFalse(row._reconcile())
        self.assertFalse(row.commission_payment_id)
        self.assertEqual(row.state, "imported")

    def test_amount_exceeding_bill_is_left_for_review(self):
        bill = self._invoice(amount=100)
        row = self._row()
        self.assertFalse(row._reconcile())
        self.assertEqual(row.commission_match_state, "review")
        self.assertEqual(bill.amount_residual, 100)
        self.assertFalse(row.commission_payment_id.is_reconciled)

    def test_existing_wrong_reconciliation_is_preserved(self):
        wrong = self._invoice(number="WRONG", amount=120)
        row = self._row()
        row._reconcile()
        payment = row.commission_payment_id
        lines = (wrong.line_ids | payment.move_id.line_ids).filtered(
            lambda line: (
                line.account_type == "liability_payable" and not line.reconciled
            )
        )
        lines.reconcile()
        expected = self._invoice(amount=120)
        self.assertFalse(row._reconcile_commission_invoice())
        self.assertEqual(row.commission_match_state, "review")
        self.assertEqual(wrong.amount_residual, 0)
        self.assertEqual(expected.amount_residual, 120)

    def test_duplicate_invoice_reference_is_not_guessed(self):
        self._invoice()
        self._invoice()
        row = self._row()
        self.assertFalse(row._reconcile())
        self.assertEqual(row.commission_match_state, "review")
        self.assertFalse(row.commission_payment_id.is_reconciled)

    def test_supplier_and_currency_must_match(self):
        other = self.env["res.partner"].create({"name": "Other Supplier"})
        bill = self._invoice(partner=other)
        row = self._row()
        self.assertFalse(row._reconcile())
        self.assertEqual(row.commission_match_state, "waiting")
        self.assertEqual(bill.amount_residual, 240)
        bill = self._invoice(currency=self.env.ref("base.USD"))
        self.assertFalse(row._reconcile_commission_invoice())
        self.assertEqual(row.commission_match_state, "review")
        self.assertFalse(row.commission_payment_id.is_reconciled)

    def test_generic_reconciliation_excludes_hb_commission_payments(self):
        bill = self._invoice()
        row = self._row(number=".")
        row._reconcile()
        account_ids = bill.line_ids.filtered(
            lambda line: line.account_type == "liability_payable"
        ).account_id.ids
        domain = self.env["account.auto.reconcile"]._get_payment_lines_domain(
            bill, account_ids
        )
        self.assertIn(("payment_id.is_hepsiburada_commission", "=", False), domain)
        self.assertFalse(
            self.env["account.move.line"].search(domain)
            & row.commission_payment_id.move_id.line_ids
        )

    def test_historical_refresh_updates_status_and_reference_without_payments(self):
        row = self._row(number=".")
        self._row(key="second", number=".")
        client = Mock()
        payload = self._payload()
        payload.update({"status": "Paid", "paymentDate": "2026-09-08T00:00:00"})
        client.get_transactions.return_value = [payload]
        self.backend.last_settlement_sync = datetime(2026, 9, 8)
        refreshed, errors = self.backend._refresh_pending_settlements(client)
        self.assertFalse(errors)
        self.assertEqual(refreshed, row)
        self.assertEqual(row.payment_status, "Paid")
        self.assertEqual(row.commission_invoice_number, payload["invoiceNumber"])
        self.assertFalse(row.commission_payment_id)
        self.assertEqual(self.backend.last_settlement_sync, datetime(2026, 9, 8))
        client.get_transactions.assert_called_once_with(
            record_date_start=None,
            record_date_end=None,
            offset=0,
            limit=100,
            order_number="HB-ORDER",
        )

    def test_refresh_paginates_all_commission_rows(self):
        row = self._row(number=".")
        client = Mock()
        client.get_transactions.side_effect = [
            [self._payload(key=f"page-one-{i}") for i in range(100)],
            [self._payload()],
        ]
        refreshed, errors = self.backend._refresh_pending_settlements(client)
        self.assertFalse(errors)
        self.assertEqual(len(refreshed), 101)
        self.assertEqual(row.commission_invoice_number, "HB20269999900001")
        self.assertEqual(client.get_transactions.call_args.kwargs["offset"], 100)

    def test_refresh_preserves_closed_payment_when_reference_changes(self):
        bill = self._invoice(amount=120)
        row = self._row()
        self.assertTrue(row._reconcile())
        payment = row.commission_payment_id
        self._row(number="CHANGED")
        self.assertEqual(row.commission_payment_id, payment)
        self.assertEqual(bill.amount_residual, 0)
        self.assertEqual(row.commission_match_state, "review")

    def test_legacy_manual_review_never_creates_another_payment(self):
        row = self._row(number=".")
        row._reconcile()
        payment = row.commission_payment_id
        row.write({"requires_manual_review": True, "state": "error"})
        self._row()
        bill = self._invoice(amount=120)
        self.backend._reconcile_pending_commissions()
        self.assertEqual(row.commission_payment_id, payment)
        self.assertEqual(row.commission_match_state, "matched")
        self.assertEqual(bill.amount_residual, 0)
        self.assertTrue(row.requires_manual_review)

    def test_orderless_invoice_refresh_uses_reference_document(self):
        payload = self._payload()
        payload["orderNumber"] = None
        row = self.env["hepsiburada.settlement"]._import_settlement(
            self.backend, payload
        )
        self.assertFalse(row.order_number)
        client = Mock()
        client.get_transactions.return_value = [payload]
        refreshed, errors = self.backend._refresh_pending_settlements(client)
        self.assertFalse(errors)
        self.assertEqual(refreshed, row)
        client.get_transactions.assert_called_once_with(
            record_date_start=None,
            record_date_end=None,
            offset=0,
            limit=100,
            reference_document=payload["invoiceNumber"],
        )
