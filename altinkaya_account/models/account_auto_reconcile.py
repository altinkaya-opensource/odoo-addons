# Copyright (C) 2025 Ahmet Yigit Budak (https://github.com/yibudak)
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

from odoo import fields, models

_logger = logging.getLogger(__name__)

CURRENCY_DIFF_JOURNALS = ("KRDGR", "KRFRK", "KFARK")
RECONCILE_FROM_DATE = "2025-01-01"
RESIDUAL_TOLERANCE = 1.0  # Max 1 unit difference for exact match ADVR
MATCH_THRESHOLD = 0.90  # 90% match required for N:1 and 1:N scenarios


class AccountAutoReconcile(models.AbstractModel):
    _name = "account.auto.reconcile"
    _description = "Account Auto Reconcile"

    # ==========================================
    # HELPER METHODS
    # ==========================================

    def _get_payment_lines_domain(self, move, pay_term_account_ids):
        """Build domain to find matching payment lines for an invoice."""
        domain = [
            ("account_id", "in", pay_term_account_ids),
            ("parent_state", "=", "posted"),
            ("partner_id", "=", move.commercial_partner_id.id),
            ("reconciled", "=", False),
            ("journal_id.code", "not in", CURRENCY_DIFF_JOURNALS + ("ADVR",)),
            ("id", "not in", move.line_ids.ids),
            ("date", ">=", RECONCILE_FROM_DATE),
            "|",
            ("amount_residual", "!=", 0.0),
            ("amount_residual_currency", "!=", 0.0),
        ]

        # Payments have opposite balance direction
        if move.is_inbound():  # Customer invoice/refund
            domain.append(("balance", "<", 0.0))
        else:  # Supplier invoice/refund
            domain.append(("balance", ">", 0.0))

        return domain

    def _find_invoices_for_payment(
        self, payment_line, current_move, account, currency=None
    ):
        """Find other invoices that could be covered by this payment.

        Args:
            currency: When set, compare amounts in this foreign currency
                      instead of company currency.
        """
        if currency:
            payment_amount = abs(payment_line.amount_residual_currency)
            current_invoice_amount = abs(
                sum(
                    current_move.line_ids.filtered(
                        lambda l: l.account_id.account_type
                        in ("asset_receivable", "liability_payable")
                        and not l.reconciled
                    ).mapped("amount_residual_currency")
                )
            )
        else:
            payment_amount = abs(payment_line.amount_residual)
            current_invoice_amount = abs(current_move.amount_residual)

        remaining = payment_amount - current_invoice_amount

        if remaining <= 0:
            return self.env["account.move"]

        # Find other unpaid invoices for same partner
        invoice_domain = [
            ("id", "!=", current_move.id),
            ("state", "=", "posted"),
            ("move_type", "=", current_move.move_type),
            ("payment_state", "in", ("not_paid", "partial")),
            ("commercial_partner_id", "=", current_move.commercial_partner_id.id),
            ("date", ">=", RECONCILE_FROM_DATE),
        ]
        if currency:
            invoice_domain.append(("currency_id", "=", currency.id))

        other_invoices = self.env["account.move"].search(
            invoice_domain, order="invoice_date asc"
        )

        # Select invoices that fit within remaining payment amount
        selected = self.env["account.move"]
        for inv in other_invoices:
            if currency:
                # Use pay term lines' residual_currency for accuracy
                inv_pay_lines = inv.line_ids.filtered(
                    lambda l: l.account_id.account_type
                    in ("asset_receivable", "liability_payable")
                    and not l.reconciled
                )
                inv_amount = abs(sum(inv_pay_lines.mapped("amount_residual_currency")))
            else:
                inv_amount = abs(inv.amount_residual)
            if inv_amount <= remaining:
                selected |= inv
                remaining -= inv_amount
                if remaining <= 0:
                    break

        return selected

    # ==========================================
    # ADVR CREATION
    # ==========================================

    def _create_advr_for_line(self, line):
        """Create ADVR entry with reversal to close residual amount.

        ADVR (Advance/Devir) is a carry-forward record that offsets small residuals
        to achieve full reconciliation. It creates a journal entry and its reversal,
        then reconciles with the original line.
        """
        # Skip lines from ADVR or currency difference journals to prevent chains
        skip_journals = ("ADVR",) + CURRENCY_DIFF_JOURNALS
        if line.journal_id.code in skip_journals:
            _logger.debug(
                "Skipping ADVR for %s - already from %s journal",
                line.move_id.name,
                line.journal_id.code,
            )
            return False

        advr_journal = self.env["account.journal"].search(
            [("code", "=", "ADVR")], limit=1
        )
        devir_account = self.env["account.account"].search(
            [("code", "=like", "100.D%")], limit=1
        )

        if not advr_journal or not devir_account:
            _logger.warning("ADVR journal or 100.D account not found")
            return False

        residual = line.amount_residual
        residual_currency = line.amount_residual_currency
        currency = line.currency_id
        company_currency = line.company_currency_id
        is_foreign = currency and currency != company_currency

        if abs(residual) < 0.01:
            return False

        # Determine debit/credit based on residual direction
        if residual > 0:
            # Positive residual on receivable = customer owes us
            recv_debit, recv_credit = 0, abs(residual)
            devir_debit, devir_credit = abs(residual), 0
        else:
            # Negative residual = we owe (credit note or overpayment)
            recv_debit, recv_credit = abs(residual), 0
            devir_debit, devir_credit = 0, abs(residual)

        recv_line_vals = {
            "account_id": line.account_id.id,
            "partner_id": line.partner_id.id,
            "debit": recv_debit,
            "credit": recv_credit,
            "name": f"ADVR - {line.move_id.name}",
        }
        devir_line_vals = {
            "account_id": devir_account.id,
            "partner_id": line.partner_id.id,
            "debit": devir_debit,
            "credit": devir_credit,
            "name": f"ADVR - {line.move_id.name}",
        }

        if is_foreign:
            recv_line_vals["currency_id"] = currency.id
            recv_line_vals["amount_currency"] = -residual_currency
            devir_line_vals["currency_id"] = currency.id
            devir_line_vals["amount_currency"] = residual_currency

        advr_move = self.env["account.move"].create(
            {
                "move_type": "entry",
                "journal_id": advr_journal.id,
                "date": fields.Date.today(),
                "ref": f"ADVR - {line.move_id.name}",
                "partner_id": line.partner_id.id,
                "line_ids": [
                    (0, 0, recv_line_vals),
                    (0, 0, devir_line_vals),
                ],
            }
        )
        advr_move.action_post()

        # Create reversal directly (avoid account.move.reversal wizard
        # whose default_get is context-sensitive and fragile)
        reverse_moves = advr_move._reverse_moves(
            [{"date": advr_move.date, "ref": f"ADVR REV - {line.move_id.name}"}],
            cancel=False,
        )
        reverse_moves.filtered(lambda m: m.state == "draft").action_post()

        # Reconcile ADVR line with original
        # Use no_exchange_difference to prevent KRFRK creation - ADVR residuals
        # are not due to exchange rates, they're rounding/matching differences
        advr_line = advr_move.line_ids.filtered(
            lambda l: l.account_id == line.account_id
        )
        if advr_line:
            (line + advr_line).with_context(no_exchange_difference=True).reconcile()

        _logger.info("Created ADVR for %s: %.2f", line.move_id.name, residual)
        return True

    def _create_advr_for_residual_invoice_lines(self, pay_term_lines):
        """Create ADVR entries for invoice lines that still have residual.

        Only targets invoice pay term lines, not payment lines.
        Payment residuals should remain available for other invoices.
        """
        pay_term_lines.invalidate_recordset(["amount_residual", "reconciled"])
        remaining = pay_term_lines.filtered(
            lambda l: not l.reconciled and abs(l.amount_residual) > 0.01
        )
        for line in remaining:
            self._create_advr_for_line(line)

    # ==========================================
    # SCENARIO 1: EXACT MATCH (1:1)
    # ==========================================

    def _try_exact_match_reconcile(self, move, pay_term_lines):
        """Find payment with exact or near-exact matching amount.

        Supports cross-currency matching (e.g., USD invoice paid with TRY).
        If difference is under RESIDUAL_TOLERANCE (1 unit), reconcile and create
        ADVR for the residual to achieve full reconciliation.

        Returns True if reconciliation successful.
        """
        domain = self._get_payment_lines_domain(move, pay_term_lines.account_id.ids)
        payment_lines = self.env["account.move.line"].search(domain)

        for payment_line in payment_lines:
            # Compare amounts based on currency match
            # Same currency: compare foreign currency amounts
            # Different currency: compare company currency amounts (TRY)
            if payment_line.currency_id == move.currency_id:
                payment_amount = abs(payment_line.amount_residual_currency)
                invoice_amount = abs(
                    sum(pay_term_lines.mapped("amount_residual_currency"))
                )
            else:
                # Cross-currency: compare in company currency (TRY)
                payment_amount = abs(payment_line.amount_residual)
                invoice_amount = abs(move.amount_residual)

            diff = abs(payment_amount - invoice_amount)

            if diff <= RESIDUAL_TOLERANCE:
                try:
                    lines_to_reconcile = payment_line + pay_term_lines
                    lines_to_reconcile.reconcile()

                    _logger.info(
                        "Exact match: Invoice %s with payment %s (diff: %.2f)",
                        move.name,
                        payment_line.move_id.name,
                        diff,
                    )

                    # Create ADVR for invoice residual if not fully matched
                    if diff > 0.01:
                        self._create_advr_for_residual_invoice_lines(pay_term_lines)

                    return True
                except Exception as e:
                    _logger.error("Exact match failed for %s: %s", move.name, e)
                    continue

        return False

    # ==========================================
    # SCENARIO 2: MANY PAYMENTS TO ONE INVOICE (N:1)
    # ==========================================

    def _try_many_payments_to_one_invoice(self, move, pay_term_lines):
        """Reconcile multiple payments against single invoice.

        Use case: Customer pays invoice in installments.
        Selects payments up to invoice amount, creates ADVR for any shortfall.
        """
        domain = self._get_payment_lines_domain(move, pay_term_lines.account_id.ids)
        all_payment_lines = self.env["account.move.line"].search(
            domain, order="date asc, id asc"
        )

        if not all_payment_lines:
            return False

        # Use foreign currency when invoice is in foreign currency
        use_foreign = move.currency_id and move.currency_id != move.company_currency_id

        if use_foreign:
            invoice_amount = abs(sum(pay_term_lines.mapped("amount_residual_currency")))
        else:
            invoice_amount = abs(move.amount_residual)

        if invoice_amount == 0:
            return False

        # Select payments up to invoice amount (don't grab excess payments)
        selected_payments = self.env["account.move.line"]
        running_total = 0.0

        for payment_line in all_payment_lines:
            if use_foreign and payment_line.currency_id == move.currency_id:
                payment_amount = abs(payment_line.amount_residual_currency)
            else:
                payment_amount = abs(payment_line.amount_residual)
            selected_payments |= payment_line
            running_total += payment_amount

            # Stop once we've reached or exceeded invoice amount
            if running_total >= invoice_amount:
                break

        if not selected_payments:
            return False

        try:
            lines_to_reconcile = pay_term_lines + selected_payments
            lines_to_reconcile.reconcile()

            match_percentage = min(running_total, invoice_amount) / invoice_amount
            _logger.info(
                "N:1 reconcile: Invoice %s with %d payments (%.1f%% match)",
                move.name,
                len(selected_payments),
                match_percentage * 100,
            )

            # ADVR only for near-matches (>=90%), skip for large gaps
            if match_percentage >= MATCH_THRESHOLD:
                self._create_advr_for_residual_invoice_lines(pay_term_lines)

            return True
        except Exception as e:
            _logger.error("N:1 reconciliation failed for %s: %s", move.name, e)
            return False

    # ==========================================
    # SCENARIO 3: ONE PAYMENT TO MANY INVOICES (1:N)
    # ==========================================

    def _try_one_payment_to_many_invoices(self, move, pay_term_lines):
        """Check if a larger payment can cover this invoice plus others.

        Supports cross-currency matching (e.g., TRY payment for USD invoices).
        Use case: Customer sends bulk payment covering multiple invoices.
        Requires 90% match threshold, creates ADVR for residual.
        """
        domain = self._get_payment_lines_domain(move, pay_term_lines.account_id.ids)
        payment_lines = self.env["account.move.line"].search(domain)

        # Use foreign currency when invoice is in foreign currency
        use_foreign = move.currency_id and move.currency_id != move.company_currency_id

        if use_foreign:
            invoice_amount = abs(sum(pay_term_lines.mapped("amount_residual_currency")))
        else:
            invoice_amount = abs(move.amount_residual)

        for payment_line in payment_lines:
            if use_foreign and payment_line.currency_id == move.currency_id:
                payment_amount = abs(payment_line.amount_residual_currency)
            else:
                payment_amount = abs(payment_line.amount_residual)

            # Payment must be larger than invoice
            if payment_amount <= invoice_amount:
                continue

            # Find other invoices this payment could cover
            foreign_currency = move.currency_id if use_foreign else None
            other_invoices = self._find_invoices_for_payment(
                payment_line, move, pay_term_lines.account_id, foreign_currency
            )

            # Calculate total invoice amount (current + others)
            total_invoice_amount = invoice_amount
            all_invoice_lines = pay_term_lines

            for other_move in other_invoices:
                other_lines = other_move.line_ids.filtered(
                    lambda line: line.account_id.account_type
                    in ("asset_receivable", "liability_payable")
                    and not line.reconciled
                )
                all_invoice_lines |= other_lines
                if use_foreign:
                    total_invoice_amount += abs(
                        sum(other_lines.mapped("amount_residual_currency"))
                    )
                else:
                    total_invoice_amount += abs(other_move.amount_residual)

            # Calculate match percentage
            potential_match = min(payment_amount, total_invoice_amount)
            max_amount = max(payment_amount, total_invoice_amount)
            if max_amount == 0:
                continue
            match_percentage = potential_match / max_amount

            # Skip if below 90% threshold
            if match_percentage < MATCH_THRESHOLD:
                _logger.debug(
                    "1:N skip: Payment %s match %.1f%% < %.0f%%",
                    payment_line.move_id.name,
                    match_percentage * 100,
                    MATCH_THRESHOLD * 100,
                )
                continue

            try:
                lines_to_reconcile = payment_line + all_invoice_lines
                lines_to_reconcile.reconcile()

                _logger.info(
                    "1:N reconcile: Payment %s with %d invoices (%.1f%% match)",
                    payment_line.move_id.name,
                    len(other_invoices) + 1,
                    match_percentage * 100,
                )

                # ADVR for shortfall when payment doesn't fully cover invoices
                if payment_amount < total_invoice_amount:
                    self._create_advr_for_residual_invoice_lines(all_invoice_lines)

                return True
            except Exception as e:
                _logger.error("1:N reconciliation failed: %s", e)
                continue

        return False

    # ==========================================
    # PUBLIC METHOD FOR WIZARD
    # ==========================================

    def reconcile_partner(self, partner):
        """Reconcile all lines for a specific partner using invoice-centric approach.

        This method is called by the wizard to reconcile a single partner.

        Args:
            partner: res.partner record (commercial partner)

        Returns:
            bool: True if any reconciliation was made
        """
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
                ("date", ">=", RECONCILE_FROM_DATE),
                ("commercial_partner_id", "=", partner.id),
            ],
            order="invoice_date asc",
        )

        reconciled_any = False
        for move in invoices:
            pay_term_lines = move.line_ids.filtered(
                lambda line: line.account_id.account_type
                in ("asset_receivable", "liability_payable")
                and not line.reconciled
            )
            if not pay_term_lines:
                continue

            # Scenario 1: Exact match (1:1)
            if self._try_exact_match_reconcile(move, pay_term_lines):
                reconciled_any = True
                continue

            # Scenario 2: Many payments to one invoice (N:1)
            if self._try_many_payments_to_one_invoice(move, pay_term_lines):
                reconciled_any = True
                continue

            # Scenario 3: One payment to many invoices (1:N)
            if self._try_one_payment_to_many_invoices(move, pay_term_lines):
                reconciled_any = True

        return reconciled_any

    # ==========================================
    # MAIN CRON METHOD
    # ==========================================

    def _cron_try_auto_reconcile_move_lines(self):
        """Invoice-centric auto-reconcile.

        For each unpaid invoice:
        1. Try exact match (1:1) - ADVR for diff under 1 unit
        2. Try many payments to one invoice (N:1) - ADVR for shortfall
        3. Try one payment to many invoices (1:N) - 90% threshold + ADVR
        """
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
                ("date", ">=", RECONCILE_FROM_DATE),
            ],
            order="invoice_date asc",
        )

        _logger.info("Auto-reconcile: Processing %d invoices", len(invoices))

        for move in invoices:
            pay_term_lines = move.line_ids.filtered(
                lambda line: line.account_id.account_type
                in ("asset_receivable", "liability_payable")
                and not line.reconciled
            )
            if not pay_term_lines:
                continue

            # Scenario 1: Exact match (1:1)
            if self._try_exact_match_reconcile(move, pay_term_lines):
                continue

            # Scenario 2: Many payments to one invoice (N:1)
            if self._try_many_payments_to_one_invoice(move, pay_term_lines):
                continue

            # Scenario 3: One payment to many invoices (1:N)
            self._try_one_payment_to_many_invoices(move, pay_term_lines)
