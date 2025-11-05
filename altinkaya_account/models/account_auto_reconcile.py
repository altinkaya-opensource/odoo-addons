# Copyright (C) 2025 Ahmet Yiğit Budak (https://github.com/yibudak)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
import logging

from odoo import models
from odoo.exceptions import ValidationError
from odoo.tools import float_compare

_logger = logging.getLogger(__name__)


WRITEOFF_THRESHOLD = 5.0
WRITEOFF_ACCOUNT_CODE = "679"
PARTIAL_MIN_PERCENTAGE = 10.0
ROUNDING_PRECISION = 0.1
CURRENCY_DIFF_JOURNALS = ("KRDGR", "KRFRK", "KFARK")


class AccountAutoReconcile(models.AbstractModel):
    _name = "account.auto.reconcile"
    _description = "Account Auto Reconcile"

    def _get_payment_lines_domain(self, move, pay_term_account_ids):
        domain = [
            ("account_id", "in", pay_term_account_ids),
            ("parent_state", "=", "posted"),
            ("partner_id", "=", move.commercial_partner_id.id),
            ("reconciled", "=", False),
            ("journal_id.code", "not in", CURRENCY_DIFF_JOURNALS),
            ("id", "not in", move.line_ids.ids),
            "|",
            ("amount_residual", "!=", 0.0),
            ("amount_residual_currency", "!=", 0.0),
        ]

        if move.is_inbound():
            domain.append(("balance", "<", 0.0))
        else:
            domain.append(("balance", ">", 0.0))

        return domain

    def _try_many_payments_to_one_invoice(self, move, pay_term_lines):
        domain = self._get_payment_lines_domain(move, pay_term_lines.account_id.ids)

        payment_lines = self.env["account.move.line"].search(
            domain, order="date asc, id asc"
        )

        if not payment_lines:
            return False

        total_payment = abs(sum(payment_lines.mapped("amount_residual")))
        invoice_amount = abs(move.amount_residual)

        min_required = invoice_amount * (PARTIAL_MIN_PERCENTAGE / 100.0)
        if total_payment < min_required:
            return False

        difference = invoice_amount - total_payment

        writeoff_line = self.env["account.move.line"]
        if 0 < difference < WRITEOFF_THRESHOLD:
            try:
                writeoff_entry = self._create_writeoff_entry_for_move(move)
                writeoff_line = writeoff_entry.line_ids.filtered(
                    lambda line: line.account_id.account_type
                    in ("asset_receivable", "liability_payable")
                )
                _logger.info(
                    "Created writeoff entry %s (%.2f) for invoice %s",
                    writeoff_entry.name,
                    difference,
                    move.name,
                )
            except Exception as e:
                _logger.error(
                    "Failed to create writeoff for invoice %s: %s",
                    move.name,
                    str(e),
                )

        try:
            lines_to_reconcile = pay_term_lines + payment_lines + writeoff_line
            result = lines_to_reconcile.reconcile()
            if result.get("partials"):
                _logger.info(
                    "Auto-reconciled invoice %s with %d payment(s)%s",
                    move.name,
                    len(payment_lines.move_id),
                    " and writeoff" if writeoff_line else "",
                )
                return True
        except Exception as e:
            _logger.error(
                "Many-to-one reconciliation failed for invoice %s: %s",
                move.name,
                str(e),
            )

        return False

    def _try_exact_match_reconcile(self, move, pay_term_lines):
        amount_residual = move.amount_residual
        invoice_currency = move.currency_id

        domain = self._get_payment_lines_domain(move, pay_term_lines.account_id.ids)
        payment_lines = self.env["account.move.line"].search(domain)

        for line in payment_lines:
            if line.currency_id != invoice_currency:
                continue

            if (
                float_compare(
                    abs(line.amount_residual_currency),
                    abs(amount_residual),
                    precision_rounding=ROUNDING_PRECISION,
                )
                == 0
            ):
                try:
                    (line + pay_term_lines).reconcile()
                    _logger.info(
                        "Exact match reconciliation for invoice %s with payment %s",
                        move.name,
                        line.move_id.name,
                    )
                    return True
                except Exception as e:
                    _logger.error(
                        "Exact match reconciliation failed for %s: %s",
                        move.name,
                        str(e),
                    )
                    continue

        return False

    def _cron_try_auto_reconcile_move_lines(self):
        invoices = self.env["account.move"].search(
            [
                ("state", "=", "posted"),
                (
                    "move_type",
                    "in",
                    ["out_invoice", "out_refund", "in_invoice", "in_refund"],
                ),
                ("payment_state", "in", ("not_paid", "partial")),
                ("journal_id.code", "not in", CURRENCY_DIFF_JOURNALS),
            ],
            order="invoice_date desc",
        )
        for move in invoices:
            pay_term_lines = move.line_ids.filtered(
                lambda line: line.account_id.account_type
                in ("asset_receivable", "liability_payable")
                and not line.reconciled
            )

            if not pay_term_lines:
                continue

            # Scenario 1: Exact match
            if self._try_exact_match_reconcile(move, pay_term_lines):
                continue

            # Scenario 2: Many payments -> one invoice (with 10% threshold)
            if self._try_many_payments_to_one_invoice(move, pay_term_lines):
                move.invalidate_recordset(fnames=["payment_state", "amount_residual"])
                if move.payment_state == "paid":
                    continue

            # Scenario 3: Write-off small amounts
            move.invalidate_recordset(fnames=["amount_residual_signed"])
            amount_residual_signed = abs(move.amount_residual_signed)

            if (
                amount_residual_signed > 0
                and float_compare(
                    amount_residual_signed,
                    WRITEOFF_THRESHOLD,
                    precision_rounding=0.01,
                )
                <= 0
            ):
                try:
                    writeoff_entry = self._create_writeoff_entry_for_move(move)
                    line_to_reconcile = writeoff_entry.line_ids.filtered(
                        lambda line: line.account_id.account_type
                        in ("asset_receivable", "liability_payable")
                    )
                    (line_to_reconcile + pay_term_lines).reconcile()
                    _logger.info(
                        "Write-off reconciliation for invoice %s, amount: %.2f",
                        move.name,
                        amount_residual_signed,
                    )
                except Exception as e:
                    _logger.error(
                        "Write-off reconciliation failed for %s: %s",
                        move.name,
                        str(e),
                    )

    def _create_writeoff_entry_for_move(self, move):
        writeoff_journal = move.journal_id
        writeoff_account = self.env["account.account"].search(
            [("code", "=", WRITEOFF_ACCOUNT_CODE)], limit=1
        )
        if not writeoff_account:
            raise ValidationError(
                "Please define an account with code"
                f"'{WRITEOFF_ACCOUNT_CODE}' for write-offs."
            )

        writeoff_amount = move.amount_residual_signed
        if move.is_outbound():
            writeoff_amount *= -1

        writeoff_entry = self.env["account.move"].create(
            {
                "move_type": "entry",
                "journal_id": writeoff_journal.id,
                "date": move.date,
                "partner_id": move.partner_id.id,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "account_id": writeoff_account.id,
                            "debit": writeoff_amount if writeoff_amount > 0 else 0.0,
                            "credit": -writeoff_amount if writeoff_amount < 0 else 0.0,
                            "name": f"{move.name} Write-off",
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "account_id": move.line_ids.filtered(
                                lambda line: line.account_id.account_type
                                in ("asset_receivable", "liability_payable")
                            ).account_id.id,
                            "debit": -writeoff_amount if writeoff_amount < 0 else 0.0,
                            "credit": writeoff_amount if writeoff_amount > 0 else 0.0,
                            "name": f"{move.name} Write-off",
                        },
                    ),
                ],
            }
        )
        writeoff_entry.action_post()
        return writeoff_entry
