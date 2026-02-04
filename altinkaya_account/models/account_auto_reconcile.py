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
RECONCILE_FROM_DATE = "2022-01-01"
MATCH_THRESHOLD = 0.95  # 95% match required
RESIDUAL_TOLERANCE = 1.0  # Max 1 TRY for ADVR


class AccountAutoReconcile(models.AbstractModel):
    _name = "account.auto.reconcile"
    _description = "Account Auto Reconcile"

    # ==========================================
    # HELPER METHODS
    # ==========================================

    def _get_partners_with_unreconciled_lines(self):
        """Get partners with unreconciled receivable/payable lines."""
        self.env.cr.execute(
            """
            SELECT DISTINCT rp.commercial_partner_id
            FROM account_move_line aml
            JOIN res_partner rp ON rp.id = aml.partner_id
            JOIN account_account aa ON aa.id = aml.account_id
            JOIN account_move am ON am.id = aml.move_id
            JOIN account_journal aj ON aj.id = aml.journal_id
            WHERE aa.account_type IN ('asset_receivable', 'liability_payable')
            AND aml.reconciled = FALSE
            AND am.state = 'posted'
            AND aml.date >= %s
            AND aj.code NOT IN %s
            AND (aml.amount_residual != 0 OR aml.amount_residual_currency != 0)
            """,
            (RECONCILE_FROM_DATE, CURRENCY_DIFF_JOURNALS),
        )

        partner_ids = [row[0] for row in self.env.cr.fetchall() if row[0]]
        return self.env["res.partner"].browse(partner_ids)

    def _get_partner_unreconciled_lines(self, partner):
        """Get all unreconciled lines for a partner."""
        return self.env["account.move.line"].search(
            [
                ("partner_id.commercial_partner_id", "=", partner.id),
                (
                    "account_id.account_type",
                    "in",
                    ("asset_receivable", "liability_payable"),
                ),
                ("reconciled", "=", False),
                ("parent_state", "=", "posted"),
                ("date", ">=", RECONCILE_FROM_DATE),
                ("journal_id.code", "not in", CURRENCY_DIFF_JOURNALS),
                "|",
                ("amount_residual", "!=", 0.0),
                ("amount_residual_currency", "!=", 0.0),
            ]
        )

    # ==========================================
    # TYPE A: EXACT MATCH
    # ==========================================

    def _try_exact_match_for_partner(self, partner, lines):
        """Try exact match reconciliation for a partner's lines.

        Returns True if any exact match was made.
        """
        # Separate by balance direction
        debit_lines = lines.filtered(lambda l: l.balance > 0)
        credit_lines = lines.filtered(lambda l: l.balance < 0)

        matched = False
        for debit_line in debit_lines:
            if debit_line.reconciled:
                continue

            for credit_line in credit_lines:
                if credit_line.reconciled:
                    continue

                # Must be same currency
                if debit_line.currency_id != credit_line.currency_id:
                    continue

                # Check amount match (within 1 TRY tolerance)
                debit_amount = abs(debit_line.amount_residual_currency)
                credit_amount = abs(credit_line.amount_residual_currency)
                diff = abs(debit_amount - credit_amount)

                if diff <= RESIDUAL_TOLERANCE:
                    # Reconcile these two lines
                    (debit_line + credit_line).reconcile()

                    # If there's a residual, create ADVR
                    debit_line.invalidate_recordset(["amount_residual"])
                    if abs(debit_line.amount_residual) > 0.01:
                        self._create_advr_for_line(debit_line)

                    _logger.info(
                        "Exact match: %s <-> %s (diff: %.2f)",
                        debit_line.move_id.name,
                        credit_line.move_id.name,
                        diff,
                    )
                    matched = True
                    break

        return matched

    # ==========================================
    # TYPE B: SESSIONAL RECONCILIATION
    # ==========================================

    def _try_sessional_reconcile(self, partner, force=False):
        """Sessional reconciliation for a partner.

        Gathers all unreconciled lines and checks if we can achieve 95% match.
        If yes, reconcile all and create ADVR for residual.
        If no, skip entirely (don't create orphaned partials).

        Args:
            partner: res.partner record
            force: If True, skip the 95% threshold and reconcile anyway
        """
        lines = self._get_partner_unreconciled_lines(partner)
        if not lines:
            return False

        # Group by account (must reconcile within same account)
        account_lines = {}
        for line in lines:
            acc_id = line.account_id.id
            if acc_id not in account_lines:
                account_lines[acc_id] = self.env["account.move.line"]
            account_lines[acc_id] |= line

        reconciled_any = False

        for _account_id, acc_lines in account_lines.items():
            # Calculate totals
            total_debit = sum(l.balance for l in acc_lines if l.balance > 0)
            total_credit = abs(sum(l.balance for l in acc_lines if l.balance < 0))
            total_amount = max(total_debit, total_credit)

            if total_amount == 0:
                continue

            # Calculate potential match
            potential_match = min(total_debit, total_credit)
            match_percentage = potential_match / total_amount

            # Skip if below threshold (unless force=True)
            if not force and match_percentage < MATCH_THRESHOLD:
                _logger.info(
                    "Partner %s account %s: match %.1f%% < 95%%, skipping",
                    partner.name,
                    acc_lines[0].account_id.code,
                    match_percentage * 100,
                )
                continue

            # Has both debits and credits?
            has_debits = any(l.balance > 0 for l in acc_lines)
            has_credits = any(l.balance < 0 for l in acc_lines)

            if not (has_debits and has_credits):
                # Only one side - if force, create ADVR for each line
                if force:
                    for line in acc_lines:
                        if abs(line.amount_residual) > 0.01:
                            self._create_advr_for_line(line)
                    reconciled_any = True
                continue

            # Reconcile all lines at once
            acc_lines.reconcile()

            # Check for residual and create ADVR
            acc_lines.invalidate_recordset(["amount_residual", "reconciled"])
            remaining = acc_lines.filtered(
                lambda l: not l.reconciled and abs(l.amount_residual) > 0.01
            )

            for line in remaining:
                self._create_advr_for_line(line)

            _logger.info(
                "Sessional: Partner %s, account %s, %d lines, %.1f%% match%s",
                partner.name,
                acc_lines[0].account_id.code,
                len(acc_lines),
                match_percentage * 100,
                " (forced)" if force else "",
            )
            reconciled_any = True

        return reconciled_any

    # ==========================================
    # ADVR CREATION
    # ==========================================

    def _create_advr_for_line(self, line):
        """Create ADVR entry with reversal to close residual amount."""
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
        if abs(residual) < 0.01:
            return False

        # Determine debit/credit
        if residual > 0:
            # Positive residual on receivable = customer owes us
            recv_debit, recv_credit = 0, abs(residual)
            devir_debit, devir_credit = abs(residual), 0
        else:
            # Negative residual = we owe (credit note or overpayment)
            recv_debit, recv_credit = abs(residual), 0
            devir_debit, devir_credit = 0, abs(residual)

        advr_move = self.env["account.move"].create(
            {
                "move_type": "entry",
                "journal_id": advr_journal.id,
                "date": fields.Date.today(),
                "ref": f"ADVR - {line.move_id.name}",
                "partner_id": line.partner_id.id,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "account_id": line.account_id.id,
                            "partner_id": line.partner_id.id,
                            "debit": recv_debit,
                            "credit": recv_credit,
                            "name": f"ADVR - {line.move_id.name}",
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "account_id": devir_account.id,
                            "partner_id": line.partner_id.id,
                            "debit": devir_debit,
                            "credit": devir_credit,
                            "name": f"ADVR - {line.move_id.name}",
                        },
                    ),
                ],
            }
        )
        advr_move.action_post()

        # Create reversal
        reversal = self.env["account.move.reversal"].create(
            {
                "move_ids": [(6, 0, [advr_move.id])],
                "journal_id": advr_journal.id,
                "date_mode": "entry",
            }
        )
        reversal.reverse_moves()
        reversal.new_move_ids.filtered(lambda m: m.state == "draft").action_post()

        # Reconcile ADVR line with original
        advr_line = advr_move.line_ids.filtered(
            lambda l: l.account_id == line.account_id
        )
        if advr_line:
            (line + advr_line).reconcile()

        _logger.info("Created ADVR for %s: %.2f", line.move_id.name, residual)
        return True

    # ==========================================
    # NIGHTLY CLEANUP CRON
    # ==========================================

    def _cron_unlink_incomplete_partials(self):
        """Nightly cleanup: Unlink all partials without full_reconcile_id.

        This ensures no orphaned partial reconciles remain in the system.
        Unlinking partials automatically deletes associated KRFRK moves
        via Odoo's cascade delete on exchange_move_id.
        """
        amls = self.env["account.move.line"].search(
            [
                "|",
                ("matched_credit_ids", "!=", False),
                ("matched_debit_ids", "!=", False),
                ("full_reconcile_id", "=", False),
            ]
        )

        partial_recs = self.env["account.partial.reconcile"]
        for aml in amls:
            partial_recs |= aml.matched_credit_ids
            partial_recs |= aml.matched_debit_ids

        if partial_recs:
            _logger.info("Unlinking %d incomplete partials", len(partial_recs))
            partial_recs.unlink()

    # ==========================================
    # PUBLIC METHOD FOR WIZARD
    # ==========================================

    def reconcile_partner(self, partner, force=False):
        """Reconcile all lines for a specific partner.

        This method is called by the wizard to reconcile a single partner.

        Args:
            partner: res.partner record (commercial partner)
            force: If True, skip 95% threshold and create ADVR for residuals

        Returns:
            bool: True if any reconciliation was made
        """
        lines = self._get_partner_unreconciled_lines(partner)
        if not lines:
            return False

        # Step 1: Try exact matches first
        self._try_exact_match_for_partner(partner, lines)

        # Step 2: Try sessional reconciliation for remaining
        return self._try_sessional_reconcile(partner, force=force)

    # ==========================================
    # MAIN CRON METHOD
    # ==========================================

    def _cron_try_auto_reconcile_move_lines(self, force=False):
        """Main auto-reconcile cron job.

        New approach:
        1. Iterate over partners with unreconciled lines
        2. For each partner, try exact matches first
        3. Then try sessional reconciliation (95% threshold)
        4. Always end with full_reconcile_id (via ADVR if needed)
        5. If can't achieve 95%, skip entirely (unless force=True)

        Args:
            force: If True, skip 95% threshold and reconcile anyway
        """
        partners = self._get_partners_with_unreconciled_lines()
        _logger.info("Auto-reconcile: Processing %d partners", len(partners))

        for partner in partners:
            self.reconcile_partner(partner, force=force)
