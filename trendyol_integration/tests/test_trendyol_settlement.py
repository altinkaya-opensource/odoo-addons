# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import json
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch

from odoo import fields

from ..models.trendyol_backend import _utc_to_trendyol_ts
from ..models.trendyol_request import TrendyolAPIError
from .common import TrendyolTestCase


class TestTrendyolSettlement(TrendyolTestCase):
    def setUp(self):
        super().setUp()
        # Installed ERP stacks can shorten survey URLs during invoice posting.
        # Keep this accounting test independent of that external service.
        if "short.url.yourls" in self.env:
            self.patch(
                type(self.env["short.url.yourls"]),
                "shorten_url",
                lambda service, url: url,
            )

    def _create_settlement_row(
        self, order, settlement_id, commission_amount, invoice_number=False
    ):
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
                "raw_data": json.dumps(
                    {"commissionInvoiceSerialNumber": invoice_number}
                ),
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
        self._post_fixture_invoice(invoice)
        order = self.env["trendyol.order"].create(
            {
                "odoo_id": sale.id,
                "backend_id": self.backend.id,
                "trendyol_order_number": "SETTLEMENT-ORDER",
                "trendyol_package_id": "SETTLEMENT-PACKAGE",
            }
        )
        return order, invoice

    def _vendor_bill(self, reference, amount, date="2026-08-28", currency=False):
        """Create a posted vendor bill without tax rounding ambiguity."""
        expense = self.env["account.account"].search(
            [
                ("company_id", "=", self.env.company.id),
                ("account_type", "=", "expense"),
                ("deprecated", "=", False),
            ],
            limit=1,
        )
        bill = self.env["account.move"].create(
            {
                "move_type": "in_invoice",
                "partner_id": self.backend.trendyol_partner_id.id,
                "invoice_date": date,
                "date": date,
                "ref": reference,
                "currency_id": (currency or self.env.company.currency_id).id,
                "invoice_line_ids": [
                    (
                        0,
                        0,
                        {
                            "name": "Commission",
                            "quantity": 1,
                            "price_unit": amount,
                            "account_id": expense.id,
                            "tax_ids": [(5, 0, 0)],
                        },
                    )
                ],
            }
        )
        self._post_fixture_invoice(bill)
        # Preserve the external vendor reference independently of entry numbering.
        bill.ref = reference
        return bill

    def _post_fixture_invoice(self, invoice):
        """Post accounting fixtures independently of deployment warning rules."""
        if "ignore_exception" in invoice._fields:
            invoice.ignore_exception = True
        invoice.action_post()
        self.assertEqual(invoice.state, "posted")

    def _payable_lines(self, move):
        """Return the document's open payable lines."""
        return move.line_ids.filtered(
            lambda line: (
                line.account_type == "liability_payable" and not line.reconciled
            )
        )

    def test_commission_matches_api_invoice_instead_of_older_bill(self):
        order, invoice = self._prepare_payout_order()
        old = self._vendor_bill("DCF2026999900001", 15, "2026-01-21")
        target = self._vendor_bill("DCF2026999900002", 15)
        rows = self._create_settlement_row(
            order, "EXACT-1", 10, target.ref
        ) | self._create_settlement_row(order, "EXACT-2", 5, target.ref)
        rows[0]._reconcile()
        self.assertEqual(invoice.amount_residual, 0)
        self.assertEqual(old.amount_residual, 15)
        self.assertEqual(target.amount_residual, 0)
        self.assertEqual(rows.commission_payment_id.reconciled_bill_ids, target)
        self.assertTrue(rows.commission_payment_id.is_trendyol_commission)
        self.assertEqual(rows.mapped("commission_match_state"), ["matched", "matched"])

    def test_missing_reference_is_excluded_from_general_reconciliation(self):
        order, invoice = self._prepare_payout_order()
        old = self._vendor_bill("DCF2026999900001", 15, "2026-01-21")
        row = self._create_settlement_row(order, "WAIT-NUMBER", 15)
        action = row.action_reconcile()
        self.assertEqual(action["params"]["type"], "warning")
        commission = row.commission_payment_id
        self.env["account.auto.reconcile"].reconcile_partner(
            self.backend.trendyol_partner_id
        )
        self.assertEqual(old.amount_residual, 15)
        self.assertFalse(commission.is_reconciled)
        self.assertEqual(row.commission_match_state, "waiting")
        self.assertEqual(invoice.amount_residual, 0)

        ordinary = self.env["account.payment"].create(
            {
                "payment_type": "outbound",
                "partner_type": "supplier",
                "partner_id": self.backend.trendyol_partner_id.id,
                "amount": 15,
                "currency_id": commission.currency_id.id,
                "journal_id": commission.journal_id.id,
            }
        )
        ordinary.action_post()
        self.env["account.auto.reconcile"].reconcile_partner(
            self.backend.trendyol_partner_id
        )
        self.assertTrue(ordinary.is_reconciled)
        self.assertEqual(old.amount_residual, 0)
        self.assertFalse(commission.is_reconciled)

    def test_missing_vendor_bill_waits_then_reuses_the_same_payment(self):
        order, _invoice = self._prepare_payout_order()
        row = self._create_settlement_row(order, "WAIT-BILL", 15, "DCF2026999900002")
        row._reconcile()
        payment = row.commission_payment_id
        self.assertFalse(payment.is_reconciled)
        self.assertEqual(row.commission_match_state, "waiting")
        bill = self._vendor_bill("DCF2026999900002", 15)
        self.backend._reconcile_pending_commissions()
        row.action_reconcile_commission()
        self.assertEqual(row.commission_payment_id, payment)
        self.assertEqual(payment.reconciled_bill_ids, bill, row.commission_match_note)
        self.assertEqual(row.commission_match_state, "matched")

    def test_bulk_vendor_bill_accepts_commissions_from_multiple_orders(self):
        order, _invoice = self._prepare_payout_order()
        bill = self._vendor_bill("DCF2026999900002", 30)
        first = self._create_settlement_row(order, "BULK-1", 10, bill.ref)
        first._reconcile()
        _sale, second_order = self._create_sale_and_order(package_id="SECOND-PACKAGE")
        second = self._create_settlement_row(second_order, "BULK-2", 20, bill.ref)
        payment = second._create_commission_payment("outbound")
        second.commission_payment_id = payment
        second._reconcile_commission_invoice()
        self.assertEqual(bill.amount_residual, 0)
        self.assertTrue(first.commission_payment_id.is_reconciled)
        self.assertTrue(second.commission_payment_id.is_reconciled)
        self.assertNotEqual(first.commission_payment_id, second.commission_payment_id)

    def test_reference_refresh_revisits_old_transactions_without_new_payments(self):
        order, _invoice = self._prepare_payout_order()
        row = self._create_settlement_row(order, "REFRESH-1", 15)
        row.transaction_date = fields.Datetime.now() - timedelta(days=7)
        row._reconcile()
        payment = row.commission_payment_id
        bill = self._vendor_bill("DCF2026999900002", 15)
        previous_sync = fields.Datetime.now() - timedelta(days=1)
        self.backend.write(
            {"auto_reconcile_settlements": True, "last_settlement_sync": previous_sync}
        )
        client = SimpleNamespace(
            get_settlements=Mock(
                side_effect=[
                    {"content": [], "totalPages": 0},
                    {
                        "content": [
                            {
                                "id": row.trendyol_settlement_id,
                                "commissionInvoiceSerialNumber": bill.ref,
                            }
                        ],
                        "totalPages": 1,
                    },
                ]
            )
        )
        with patch.object(type(self.backend), "_get_api_client", return_value=client):
            self.backend._import_settlements()
        self.assertLess(
            client.get_settlements.call_args.kwargs["start_date"],
            _utc_to_trendyol_ts(previous_sync),
        )
        self.assertEqual(row.commission_invoice_number, bill.ref)
        self.assertEqual(row.commission_payment_id, payment)
        self.assertEqual(payment.reconciled_bill_ids, bill)
        self.env["trendyol.settlement"]._import_settlement(
            self.backend, {"id": row.trendyol_settlement_id}
        )
        self.assertEqual(row.commission_invoice_number, bill.ref)

    def test_daily_refresh_preserves_closed_legacy_payment_and_amounts(self):
        order, invoice = self._prepare_payout_order()
        row = self._create_settlement_row(order, "LEGACY-REFRESH", 15)
        row.transaction_date = fields.Datetime.now() - timedelta(days=180)
        row.raw_data = json.dumps({"commissionAmount": 15, "credit": 100})
        row._reconcile()
        payment = row.commission_payment_id
        old = self._vendor_bill("DCF2026999900001", 15, "2026-01-21")
        (self._payable_lines(payment.move_id) + self._payable_lines(old)).reconcile()
        original_links = (
            payment.move_id.line_ids.matched_credit_ids
            | payment.move_id.line_ids.matched_debit_ids
        )
        target = self._vendor_bill("DCF2026999900002", 15)
        self.backend.write(
            {
                "auto_reconcile_settlements": False,
                "last_settlement_sync": fields.Datetime.now() - timedelta(days=1),
            }
        )
        client = SimpleNamespace(
            get_settlements=Mock(
                side_effect=[
                    {"content": []},
                    {
                        "content": [
                            {
                                "id": row.trendyol_settlement_id,
                                "commissionInvoiceSerialNumber": target.ref,
                                "commissionAmount": 999,
                                "credit": 999,
                            },
                            {"id": "UNREQUESTED-HISTORY", "commissionAmount": 20},
                        ],
                        "totalPages": 1,
                    },
                ]
            )
        )
        with patch.object(type(self.backend), "_get_api_client", return_value=client):
            self.backend._import_settlements()
        self.assertEqual(row.commission_invoice_number, target.ref)
        self.assertEqual(row.commission_payment_id, payment)
        self.assertEqual(payment.reconciled_bill_ids, old)
        self.assertTrue(original_links.exists())
        self.assertEqual(row.state, "reconciled")
        self.assertEqual(row.commission_match_state, "review")
        self.assertEqual(row.commission_amount, 15)
        self.assertEqual(json.loads(row.raw_data)["commissionAmount"], 15)
        self.assertEqual(json.loads(row.raw_data)["credit"], 100)
        self.assertEqual(invoice.amount_residual, 0)
        self.assertEqual(target.amount_residual, 15)
        self.assertFalse(
            self.env["trendyol.settlement"].search(
                [("trendyol_settlement_id", "=", "UNREQUESTED-HISTORY")]
            )
        )

    def test_reference_refresh_pages_rows_without_payments_and_stops_when_filled(self):
        _sale, order = self._create_sale_and_order()
        row = self._create_settlement_row(order, "UNPAID-REFERENCE", 15)
        row.transaction_date = fields.Datetime.now() - timedelta(days=90)
        client = SimpleNamespace(
            get_settlements=Mock(
                side_effect=[
                    {"content": [{"id": "UNREQUESTED-HISTORY"}], "totalPages": 2},
                    {
                        "content": [
                            {
                                "id": row.trendyol_settlement_id,
                                "commissionInvoiceSerialNumber": "DCF2026999900002",
                            }
                        ],
                        "totalPages": 2,
                    },
                ]
            )
        )
        self.backend._refresh_missing_commission_references(client)
        self.assertEqual(row.commission_invoice_number, "DCF2026999900002")
        self.assertFalse(row.odoo_payment_id)
        self.assertFalse(row.commission_payment_id)
        self.assertEqual(
            [call.kwargs["page"] for call in client.get_settlements.call_args_list],
            [0, 1],
        )
        client.get_settlements.reset_mock()
        self.backend._refresh_missing_commission_references(client)
        client.get_settlements.assert_not_called()

    def test_reference_refresh_uses_sparse_windows_and_trendyol_midnight(self):
        _sale, order = self._create_sale_and_order()
        for index, date in enumerate(
            [
                "2026-01-01 22:30:00",
                "2026-01-15 22:30:00",
                "2026-01-16 22:30:00",
                "2026-07-01 22:30:00",
            ]
        ):
            row = self._create_settlement_row(order, f"WINDOW-{index}", 15)
            row.transaction_date = date
        zero = self._create_settlement_row(order, "ZERO-COMMISSION", 0)
        zero.transaction_date = "2025-01-01 12:00:00"
        known = self._create_settlement_row(order, "KNOWN-REFERENCE", 15, "KNOWN")
        known.transaction_date = "2025-02-01 12:00:00"
        other_backend = self.backend.copy({"name": "Other Reference Backend"})
        other = self._create_settlement_row(order, "OTHER-BACKEND", 15)
        other.write(
            {"backend_id": other_backend.id, "transaction_date": "2025-03-01 12:00:00"}
        )
        client = SimpleNamespace(get_settlements=Mock(return_value={"content": []}))
        self.backend._refresh_missing_commission_references(client)
        calls = client.get_settlements.call_args_list
        expected = [
            ("2026-01-02", "2026-01-17"),
            ("2026-01-17", "2026-01-18"),
            ("2026-07-02", "2026-07-03"),
        ]
        self.assertEqual(len(calls), len(expected))
        for call, (start, end) in zip(calls, expected, strict=True):
            self.assertEqual(
                call.kwargs["start_date"],
                _utc_to_trendyol_ts(fields.Datetime.to_datetime(start)),
            )
            self.assertEqual(
                call.kwargs["end_date"],
                _utc_to_trendyol_ts(fields.Datetime.to_datetime(end)),
            )

    def test_failed_reference_refresh_keeps_import_watermark(self):
        _sale, order = self._create_sale_and_order()
        row = self._create_settlement_row(order, "FAILED-REFERENCE", 15)
        row.transaction_date = fields.Datetime.now() - timedelta(days=90)
        previous_sync = fields.Datetime.now() - timedelta(days=1)
        self.backend.last_settlement_sync = previous_sync
        client = SimpleNamespace(
            get_settlements=Mock(
                side_effect=[{"content": []}, TrendyolAPIError("Finance unavailable")]
            )
        )
        with patch.object(type(self.backend), "_get_api_client", return_value=client):
            with self.assertRaises(TrendyolAPIError):
                self.backend._import_settlements()
        self.assertEqual(self.backend.last_settlement_sync, previous_sync)
        self.assertFalse(row.commission_invoice_number)
        self.assertFalse(row.commission_payment_id)

    def test_existing_open_payments_are_matched_by_commission_cron(self):
        order, _invoice = self._prepare_payout_order()
        row = self._create_settlement_row(order, "LEGACY-OPEN", 15)
        row._reconcile()
        payment = row.commission_payment_id
        bill = self._vendor_bill("DCF2026999900002", 15)
        self.env["trendyol.settlement"]._import_settlement(
            self.backend,
            {
                "id": row.trendyol_settlement_id,
                "commissionInvoiceSerialNumber": bill.ref,
            },
        )
        self.assertEqual(row.commission_match_state, "waiting")
        self.env["account.auto.reconcile"].reconcile_partner(
            self.backend.trendyol_partner_id
        )
        self.assertTrue(payment.is_trendyol_commission)
        self.assertFalse(payment.is_reconciled)
        self.assertEqual(bill.amount_residual, 15)
        self.backend._reconcile_pending_commissions()
        self.assertEqual(row.commission_payment_id, payment)
        self.assertTrue(payment.is_reconciled)
        self.assertEqual(payment.reconciled_bill_ids, bill)
        self.assertEqual(bill.amount_residual, 0)
        self.assertEqual(row.commission_match_state, "matched")

    def test_existing_match_is_preserved_until_manually_unreconciled(self):
        order, _invoice = self._prepare_payout_order()
        row = self._create_settlement_row(order, "WRONG-MATCH", 15)
        row._reconcile()
        payment = row.commission_payment_id
        old = self._vendor_bill("DCF2026999900001", 15, "2026-01-21")
        (self._payable_lines(payment.move_id) + self._payable_lines(old)).reconcile()
        original_links = (
            payment.move_id.line_ids.matched_credit_ids
            | payment.move_id.line_ids.matched_debit_ids
        )
        target = self._vendor_bill("DCF2026999900002", 15)
        self.env["trendyol.settlement"]._import_settlement(
            self.backend,
            {
                "id": row.trendyol_settlement_id,
                "commissionInvoiceSerialNumber": target.ref,
            },
        )
        row.action_reconcile_commission()
        self.assertEqual(payment.reconciled_bill_ids, old)
        self.assertTrue(original_links.exists())
        self.assertEqual(target.amount_residual, 15)
        self.assertEqual(row.commission_match_state, "review")
        self.backend._reconcile_pending_commissions()
        self.assertTrue(original_links.exists())
        original_links.unlink()
        self.backend._reconcile_pending_commissions()
        self.assertEqual(row.commission_payment_id, payment)
        self.assertEqual(payment.reconciled_bill_ids, target)
        self.assertEqual(old.amount_residual, 15)
        self.assertEqual(target.amount_residual, 0)
        self.assertEqual(row.commission_match_state, "matched")

    def test_conflicting_invoice_references_wait_for_review(self):
        order, invoice = self._prepare_payout_order()
        first = self._vendor_bill("DCF2026999900001", 10)
        second = self._vendor_bill("DCF2026999900002", 5)
        rows = self._create_settlement_row(
            order, "CONFLICT-1", 10, first.ref
        ) | self._create_settlement_row(order, "CONFLICT-2", 5, second.ref)
        rows[0]._reconcile()
        self.assertFalse(rows.commission_payment_id.is_reconciled)
        self.assertEqual(rows.mapped("commission_match_state"), ["review", "review"])
        self.assertEqual(first.amount_residual, 10)
        self.assertEqual(second.amount_residual, 5)
        self.assertEqual(invoice.amount_residual, 0)

    def test_excess_payment_and_wrong_currency_do_not_reconcile(self):
        order, _invoice = self._prepare_payout_order()
        target = self._vendor_bill("DCF2026999900002", 5)
        row = self._create_settlement_row(order, "EXCESS-1", 15, target.ref)
        row._reconcile()
        self.assertEqual(row.commission_match_state, "review")
        self.assertFalse(row.commission_payment_id.is_reconciled)
        self.assertEqual(target.amount_residual, 5)
        other_currency = (
            self.env.ref("base.USD")
            if self.env.company.currency_id != self.env.ref("base.USD")
            else self.env.ref("base.EUR")
        )
        foreign = self._vendor_bill("DCF2026999900003", 15, currency=other_currency)
        row.raw_data = json.dumps({"commissionInvoiceSerialNumber": foreign.ref})
        row.action_reconcile_commission()
        self.assertEqual(row.commission_match_state, "review")
        self.assertFalse(row.commission_payment_id.is_reconciled)
        self.assertEqual(foreign.amount_residual, 15)

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
