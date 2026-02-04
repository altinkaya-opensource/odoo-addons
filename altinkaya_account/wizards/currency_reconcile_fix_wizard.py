# Copyright (C) 2026 Ahmet Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

BATCH_SIZE = 100
MIGRATION_DATE = "2022-01-01"
CURRENCY_DIFF_JOURNALS = ("KRDGR", "KRFRK", "KFARK")


class CurrencyReconcileFixWizard(models.TransientModel):
    _name = "currency.reconcile.fix.wizard"
    _description = "Fix Currency Difference Reconciliation Wizard"

    # Configuration fields
    partner_id = fields.Many2one(
        "res.partner",
        string="Specific Partner",
        help="If set, only process this partner. Leave empty for all partners.",
    )
    reconcile_from_date = fields.Date(
        default=MIGRATION_DATE,
        required=True,
        help="Re-reconcile lines from this date onwards (migration day)",
    )
    batch_size = fields.Integer(
        default=BATCH_SIZE,
        required=True,
        help="Number of records to process in each batch",
    )
    create_devir = fields.Boolean(
        string="Create Devir Entries",
        default=True,
        help="Create Devir (100.D) entries for residual amounts",
    )

    # State
    state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("analysis", "Analyzed"),
            ("phase1", "Phase 1: Unlinked Partials"),
            ("phase2", "Phase 2: Cleaned KRFRK"),
            ("phase3", "Phase 3: Re-reconciled"),
            ("phase4", "Phase 4: Created Devir"),
            ("done", "Done"),
        ],
        default="draft",
    )

    # Preview counts
    partials_to_unlink_count = fields.Integer(
        string="Partials to Unlink",
        compute="_compute_preview_counts",
    )
    exchange_moves_count = fields.Integer(
        string="Exchange Moves to Delete",
        compute="_compute_preview_counts",
    )
    lines_to_reconcile_count = fields.Integer(
        string="Lines to Re-reconcile",
        compute="_compute_preview_counts",
    )
    protected_partials_count = fields.Integer(
        string="Protected Partials (KFARK)",
        compute="_compute_preview_counts",
    )

    # Progress tracking
    phase1_processed = fields.Integer(default=0)
    phase2_processed = fields.Integer(default=0)
    phase3_processed = fields.Integer(default=0)
    phase4_processed = fields.Integer(default=0)

    # Results
    result_message = fields.Text(string="Result", readonly=True)

    # Log lines
    log_ids = fields.One2many(
        "currency.reconcile.fix.log",
        "wizard_id",
        string="Execution Log",
    )

    @api.depends("reconcile_from_date", "partner_id")
    def _compute_preview_counts(self):
        for wizard in self:
            partner_filter = ""
            partner_params = ()
            if wizard.partner_id:
                # Get commercial partner for filtering
                commercial_partner_id = wizard.partner_id.commercial_partner_id.id
                partner_filter = "AND aml.partner_id = %s"
                partner_params = (commercial_partner_id,)

            # Partials without full_reconcile_id
            self.env.cr.execute(
                f"""
                SELECT COUNT(*)
                FROM account_partial_reconcile apr
                JOIN account_move_line aml ON aml.id = apr.debit_move_id
                WHERE apr.full_reconcile_id IS NULL
                {partner_filter}
                """,
                partner_params,
            )
            wizard.partials_to_unlink_count = self.env.cr.fetchone()[0]

            # Exchange moves linked to partials (cascade delete in Phase 1)
            self.env.cr.execute(
                f"""
                SELECT COUNT(DISTINCT apr.exchange_move_id)
                FROM account_partial_reconcile apr
                JOIN account_move_line aml ON aml.id = apr.debit_move_id
                WHERE apr.full_reconcile_id IS NULL
                AND apr.exchange_move_id IS NOT NULL
                {partner_filter}
                """,
                partner_params,
            )
            cascade_exchange_moves = self.env.cr.fetchone()[0]

            # Orphan KRFRK (no partial reference) - will be deleted in Phase 2
            krfrk_journal = self.env.company.currency_exchange_journal_id
            if krfrk_journal:
                orphan_params = (krfrk_journal.id,)
                orphan_partner_filter = ""
                if wizard.partner_id:
                    orphan_partner_filter = "AND aml.partner_id = %s"
                    orphan_params = orphan_params + (commercial_partner_id,)

                self.env.cr.execute(
                    f"""
                    SELECT COUNT(DISTINCT am.id)
                    FROM account_move am
                    JOIN account_move_line aml ON aml.move_id = am.id
                    JOIN account_account aa ON aa.id = aml.account_id
                    WHERE am.journal_id = %s
                    AND am.state = 'posted'
                    AND aa.account_type IN ('asset_receivable', 'liability_payable')
                    AND aml.full_reconcile_id IS NULL
                    AND NOT EXISTS (
                        SELECT 1 FROM account_partial_reconcile apr
                        WHERE apr.exchange_move_id = am.id
                    )
                    {orphan_partner_filter}
                    """,
                    orphan_params,
                )
                orphan_krfrk_count = self.env.cr.fetchone()[0]
            else:
                orphan_krfrk_count = 0

            wizard.exchange_moves_count = cascade_exchange_moves + orphan_krfrk_count

            # Lines to reconcile from migration date
            base_params = (wizard.reconcile_from_date, CURRENCY_DIFF_JOURNALS)
            if wizard.partner_id:
                base_params = base_params + (commercial_partner_id,)
            self.env.cr.execute(
                f"""
                SELECT COUNT(*)
                FROM account_move_line aml
                JOIN account_account aa ON aa.id = aml.account_id
                JOIN account_move am ON am.id = aml.move_id
                JOIN account_journal aj ON aj.id = aml.journal_id
                WHERE aa.account_type IN ('asset_receivable', 'liability_payable')
                AND aml.reconciled = FALSE
                AND am.state = 'posted'
                AND aml.date >= %s
                AND aj.code NOT IN %s
                {"AND aml.partner_id = %s" if wizard.partner_id else ""}
                """,
                base_params,
            )
            wizard.lines_to_reconcile_count = self.env.cr.fetchone()[0]

            # Protected partials (linked to KFARK)
            self.env.cr.execute(
                f"""
                SELECT COUNT(DISTINCT apr.id)
                FROM account_partial_reconcile apr
                JOIN account_full_reconcile afr ON apr.full_reconcile_id = afr.id
                JOIN account_move_line aml ON aml.full_reconcile_id = afr.id
                JOIN account_journal aj ON aj.id = aml.journal_id
                WHERE aj.code = 'KFARK'
                {partner_filter}
                """,
                partner_params,
            )
            wizard.protected_partials_count = self.env.cr.fetchone()[0]

    def _log(self, phase, action, details, partner_id=None, amount=None):
        """Create a log entry for audit trail."""
        self.env["currency.reconcile.fix.log"].create(
            {
                "wizard_id": self.id,
                "phase": phase,
                "action": action,
                "details": details,
                "partner_id": partner_id,
                "amount": amount,
            }
        )

    def action_analyze(self):
        """Analyze the current state and prepare for execution."""
        self.ensure_one()
        self._compute_preview_counts()

        result_lines = [
            _("Analysis Complete"),
            _("=" * 40),
            _("Partials to unlink (no full_reconcile_id): %(count)d")
            % {"count": self.partials_to_unlink_count},
            _("Exchange moves to delete: %(count)d")
            % {"count": self.exchange_moves_count},
            _("Lines to re-reconcile (from %(date)s): %(count)d")
            % {
                "date": self.reconcile_from_date,
                "count": self.lines_to_reconcile_count,
            },
            _("Protected partials (KFARK linked): %(count)d")
            % {"count": self.protected_partials_count},
            _("=" * 40),
            _("Ready to proceed with Phase 1."),
        ]

        self.write(
            {
                "state": "analysis",
                "result_message": "\n".join(result_lines),
            }
        )

        self._log("analysis", "complete", "\n".join(result_lines))

        return self._return_wizard_action()

    def _unreconcile_exchange_move_lines(self, exchange_move):
        """Unreconcile all lines of an exchange move before deletion.

        When an exchange move's lines are reconciled to other entries,
        we need to remove those reconciliations first before the move
        can be deleted.
        """
        if not exchange_move:
            return

        for line in exchange_move.line_ids:
            # Get all partial reconciles involving this line
            partials_to_remove = line.matched_debit_ids | line.matched_credit_ids
            if partials_to_remove:
                self._log(
                    "phase1",
                    "unreconcile_exchange_line",
                    f"Unreconciling {len(partials_to_remove)} partials from "
                    f"exchange move line {line.id} (move: {exchange_move.name})",
                )
                # Unlink these partials (this will NOT trigger recursive exchange
                # move deletion since these are the exchange move's own lines)
                partials_to_remove.unlink()

    def action_phase1_unlink_partials(self):
        """Phase 1: Unlink all partial reconciliations without full_reconcile_id."""
        self.ensure_one()

        if self.state not in ("analysis", "draft"):
            raise UserError(_("Please run analysis first."))

        partner_info = f" for partner {self.partner_id.name}" if self.partner_id else ""
        _logger.info(
            "Phase 1: Starting unlink of incomplete partial reconciles%s", partner_info
        )

        # Build query with optional partner filter
        partner_filter = ""
        params = ()
        if self.partner_id:
            commercial_partner_id = self.partner_id.commercial_partner_id.id
            partner_filter = "AND aml.partner_id = %s"
            params = (commercial_partner_id,)

        # Get all partial IDs without full_reconcile_id
        self.env.cr.execute(
            f"""
            SELECT apr.id, apr.exchange_move_id, apr.amount,
                   apr.debit_move_id, apr.credit_move_id
            FROM account_partial_reconcile apr
            JOIN account_move_line aml ON aml.id = apr.debit_move_id
            WHERE apr.full_reconcile_id IS NULL
            {partner_filter}
            ORDER BY apr.id
            """,
            params,
        )
        partials_data = self.env.cr.fetchall()

        total_count = len(partials_data)
        processed = 0
        exchange_moves_deleted = 0
        exchange_lines_unreconciled = 0

        # Process one by one to handle exchange move unreconciliation properly
        # No try/except - any error will stop execution and rollback
        for idx, row in enumerate(partials_data):
            partial_id, exchange_move_id, amount, debit_id, credit_id = row

            partial = self.env["account.partial.reconcile"].browse(partial_id).exists()
            if not partial:
                continue

            self._log(
                "phase1",
                "unlink_partial",
                f"Partial {partial_id}: amount={amount}, "
                f"debit_line={debit_id}, credit_line={credit_id}, "
                f"exchange_move={exchange_move_id}",
                amount=amount,
            )

            # If there's an exchange move, unreconcile its lines first
            if partial.exchange_move_id:
                exchange_move = partial.exchange_move_id
                # Count lines that need unreconciliation
                for line in exchange_move.line_ids:
                    partials_count = len(
                        line.matched_debit_ids | line.matched_credit_ids
                    )
                    if partials_count > 0:
                        exchange_lines_unreconciled += partials_count

                # Unreconcile the exchange move's lines
                self._unreconcile_exchange_move_lines(exchange_move)
                exchange_moves_deleted += 1

            # Now unlink the partial (this will delete the exchange move)
            partial.unlink()
            processed += 1

            if (idx + 1) % self.batch_size == 0:
                _logger.info(
                    "Phase 1: Processed %d of %d partials",
                    idx + 1,
                    total_count,
                )

        # Also unlink orphaned ADVR moves without full_reconcile_id
        advr_deleted = self._unlink_orphan_advr_moves(partner_filter, params)

        result_lines = [
            _("Phase 1 Complete"),
            _("=" * 40),
            _("Partial reconciles removed: %(count)d") % {"count": processed},
            _("Exchange moves deleted: %(count)d") % {"count": exchange_moves_deleted},
            _("Exchange move partials unreconciled: %(count)d")
            % {"count": exchange_lines_unreconciled},
            _("Orphan ADVR moves deleted: %(count)d") % {"count": advr_deleted},
        ]

        self.write(
            {
                "state": "phase1",
                "phase1_processed": processed,
                "result_message": "\n".join(result_lines),
            }
        )

        self._log("phase1", "complete", f"Unlinked {processed} partials")

        _logger.info(
            "Phase 1: Completed - %d partials unlinked, %d ADVR deleted",
            processed,
            advr_deleted,
        )

        return self._return_wizard_action()

    def _unlink_orphan_advr_moves(self, partner_filter, params):
        """Unlink orphaned ADVR moves without full_reconcile_id.

        ADVR moves should always result in full reconciliation.
        If an ADVR move's receivable/payable line doesn't have a full_reconcile_id,
        it means the reconciliation failed and the move should be deleted.

        Returns the count of deleted moves.
        """
        advr_journal = self.env["account.journal"].search(
            [("code", "=", "ADVR")], limit=1
        )

        if not advr_journal:
            _logger.info("Phase 1: ADVR journal not found, skipping ADVR cleanup")
            return 0

        # Build query - find ADVR moves where receivable/payable line
        # doesn't have full_reconcile_id
        # Only delete ADVR records created after 2025-11-01
        advr_partner_filter = partner_filter.replace("aml.", "am.")
        self.env.cr.execute(
            f"""
            SELECT DISTINCT am.id, am.name
            FROM account_move am
            JOIN account_move_line aml ON aml.move_id = am.id
            JOIN account_account aa ON aa.id = aml.account_id
            WHERE am.journal_id = %s
            AND am.state = 'posted'
            AND am.create_date >= '2025-11-01'
            AND aa.account_type IN ('asset_receivable', 'liability_payable')
            AND aml.full_reconcile_id IS NULL
            {advr_partner_filter}
            """,
            (advr_journal.id,) + params,
        )
        orphan_advr_data = self.env.cr.fetchall()

        if not orphan_advr_data:
            _logger.info("Phase 1: No orphan ADVR moves found")
            return 0

        deleted = 0
        for move_id, move_name in orphan_advr_data:
            move = self.env["account.move"].browse(move_id).exists()
            if not move:
                continue

            self._log(
                "phase1",
                "unlink_orphan_advr",
                f"Deleting orphan ADVR move: {move_name}",
            )

            # First unreconcile any lines on this move
            for line in move.line_ids:
                partials_to_remove = line.matched_debit_ids | line.matched_credit_ids
                if partials_to_remove:
                    self._log(
                        "phase1",
                        "unreconcile_advr_line",
                        f"Unreconciling {len(partials_to_remove)} partials "
                        f"from ADVR line {line.id} (move: {move.name})",
                    )
                    partials_to_remove.unlink()

            # Skip ADVR moves that have linked bank statement lines
            # These have data integrity issues and should be handled manually
            stmt_lines = self.env["account.bank.statement.line"].search(
                [("move_id", "=", move.id)]
            )
            if stmt_lines:
                self._log(
                    "phase1",
                    "skip_advr_with_stmt_lines",
                    f"Skipping ADVR move {move.name} - has {len(stmt_lines)} "
                    f"linked statement lines",
                )
                continue

            # Cancel and delete the move
            move.button_cancel()
            move.with_context(force_delete=True).unlink()
            deleted += 1

        _logger.info("Phase 1: Deleted %d orphan ADVR moves", deleted)
        return deleted

    def action_phase2_cleanup_orphan_krfrk(self):
        """Phase 2: Cleanup orphan KRFRK moves.

        Orphan KRFRK = KRFRK moves that have NO partial reconcile pointing
        to them via exchange_move_id. These are leftover from deleted partials
        or failed reconciliations.

        Phase 1 deletes partials (which cascade deletes their KRFRK via
        exchange_move_id). This phase cleans up KRFRK that somehow lost
        their partial reconcile reference.
        """
        self.ensure_one()

        if self.state != "phase1":
            raise UserError(_("Please complete Phase 1 first."))

        partner_info = f" for partner {self.partner_id.name}" if self.partner_id else ""
        _logger.info("Phase 2: Starting cleanup of orphan KRFRK moves%s", partner_info)

        # Find KRFRK journal
        krfrk_journal = self.env.company.currency_exchange_journal_id

        if not krfrk_journal:
            self.write(
                {
                    "state": "phase2",
                    "result_message": _(
                        "Phase 2: Currency exchange journal not configured. Skipped."
                    ),
                }
            )
            return self._return_wizard_action()

        # Build query to find orphan KRFRK (no partial reconcile reference)
        partner_filter = ""
        params = (krfrk_journal.id,)

        if self.partner_id:
            partner_filter = "AND aml.partner_id = %s"
            params = params + (self.partner_id.commercial_partner_id.id,)

        self.env.cr.execute(
            f"""
            SELECT DISTINCT am.id, am.name
            FROM account_move am
            JOIN account_move_line aml ON aml.move_id = am.id
            JOIN account_account aa ON aa.id = aml.account_id
            WHERE am.journal_id = %s
            AND am.state = 'posted'
            AND aa.account_type IN ('asset_receivable', 'liability_payable')
            AND aml.full_reconcile_id IS NULL
            AND NOT EXISTS (
                SELECT 1 FROM account_partial_reconcile apr
                WHERE apr.exchange_move_id = am.id
            )
            {partner_filter}
            ORDER BY am.id
            """,
            params,
        )
        orphan_krfrk_data = self.env.cr.fetchall()

        if not orphan_krfrk_data:
            self.write(
                {
                    "state": "phase2",
                    "phase2_processed": 0,
                    "result_message": _("Phase 2: No orphan KRFRK moves found."),
                }
            )
            return self._return_wizard_action()

        total_count = len(orphan_krfrk_data)
        _logger.info("Phase 2: Found %d orphan KRFRK moves to delete", total_count)

        processed = 0
        lines_unreconciled = 0

        for idx, (move_id, move_name) in enumerate(orphan_krfrk_data):
            krfrk_move = self.env["account.move"].browse(move_id).exists()
            if not krfrk_move:
                continue

            self._log(
                "phase2",
                "delete_orphan_krfrk",
                f"Deleting orphan KRFRK: {move_name}",
            )

            # Unreconcile any lines on this KRFRK move
            for line in krfrk_move.line_ids:
                partials = line.matched_debit_ids | line.matched_credit_ids
                if partials:
                    lines_unreconciled += len(partials)
                    partials.unlink()

            # Cancel and delete the KRFRK move
            krfrk_move.button_cancel()
            krfrk_move.with_context(force_delete=True).unlink()
            processed += 1

            if (idx + 1) % self.batch_size == 0:
                _logger.info(
                    "Phase 2: Processed %d of %d orphan KRFRK moves",
                    idx + 1,
                    total_count,
                )

        result_lines = [
            _("Phase 2 Complete"),
            _("=" * 40),
            _("Orphan KRFRK moves deleted: %(count)d") % {"count": processed},
            _("Lines unreconciled: %(count)d") % {"count": lines_unreconciled},
        ]

        self.write(
            {
                "state": "phase2",
                "phase2_processed": processed,
                "result_message": "\n".join(result_lines),
            }
        )

        self._log(
            "phase2",
            "complete",
            f"Deleted {processed} orphan KRFRK moves",
        )

        _logger.info(
            "Phase 2: Completed - %d orphan KRFRK deleted, %d lines unreconciled",
            processed,
            lines_unreconciled,
        )

        return self._return_wizard_action()

    def _get_partners_with_unreconciled_lines(self):
        """Get partners with unreconciled receivable/payable lines.

        Uses account.auto.reconcile logic but allows partner filtering.
        """
        if self.partner_id:
            return self.partner_id.commercial_partner_id
        return self.env[
            "account.auto.reconcile"
        ]._get_partners_with_unreconciled_lines()

    def action_phase3_reconcile(self):
        """Phase 3: Full reconcile per partner using auto-reconcile logic.

        Uses account.auto.reconcile.reconcile_partner() with force=True
        to skip the 95% threshold and reconcile all lines with ADVR for residuals.
        """
        self.ensure_one()

        if self.state != "phase2":
            raise UserError(_("Please complete Phase 2 first."))

        partner_info = f" for partner {self.partner_id.name}" if self.partner_id else ""
        _logger.info(
            "Phase 3: Starting partner-based reconciliation from %s%s",
            self.reconcile_from_date,
            partner_info,
        )

        auto_reconcile = self.env["account.auto.reconcile"]
        partners = self._get_partners_with_unreconciled_lines()

        if not partners:
            self.write(
                {
                    "state": "phase3",
                    "phase3_processed": 0,
                    "result_message": _(
                        "Phase 3: No partners with unreconciled lines."
                    ),
                }
            )
            return self._return_wizard_action()

        total_partners = len(partners)
        partners_processed = 0

        _logger.info("Phase 3: Found %d partners to process", total_partners)

        for idx, partner in enumerate(partners):
            # Use auto_reconcile with force=True to skip 95% threshold
            if auto_reconcile.reconcile_partner(partner, force=True):
                partners_processed += 1
                self._log(
                    "phase3",
                    "reconcile",
                    f"Reconciled partner {partner.name}",
                    partner_id=partner.id,
                )

            if (idx + 1) % self.batch_size == 0:
                _logger.info(
                    "Phase 3: Processed %d/%d partners",
                    idx + 1,
                    total_partners,
                )

        result_lines = [
            _("Phase 3 Complete"),
            _("=" * 40),
            _("Total partners: %(count)d") % {"count": total_partners},
            _("Partners processed: %(count)d") % {"count": partners_processed},
        ]

        self.write(
            {
                "state": "phase3",
                "phase3_processed": partners_processed,
                "result_message": "\n".join(result_lines),
            }
        )

        self._log(
            "phase3",
            "complete",
            f"Processed {partners_processed} partners",
        )

        _logger.info("Phase 3: Completed - %d partners processed", partners_processed)

        return self._return_wizard_action()

    def action_phase4_finalize(self):
        """Phase 4: Finalize and report remaining unreconciled lines.

        Phase 3 with force=True creates ADVR for all residuals.
        This phase just reports any remaining unreconciled lines (if any).
        """
        self.ensure_one()

        if self.state != "phase3":
            raise UserError(_("Please complete Phase 3 first."))

        # Check for any remaining unreconciled lines
        domain = [
            (
                "account_id.account_type",
                "in",
                ("asset_receivable", "liability_payable"),
            ),
            ("reconciled", "=", False),
            ("parent_state", "=", "posted"),
            ("date", ">=", self.reconcile_from_date),
            ("journal_id.code", "not in", CURRENCY_DIFF_JOURNALS),
            ("amount_residual", "!=", 0),
        ]

        if self.partner_id:
            commercial_partner_id = self.partner_id.commercial_partner_id.id
            domain.insert(0, ("partner_id", "=", commercial_partner_id))

        remaining_lines = self.env["account.move.line"].search_count(domain)

        result_lines = [
            _("Wizard Complete"),
            _("=" * 40),
            _("Phase 1: Unlinked incomplete partials"),
            _("Phase 2: Cleaned orphan KRFRK"),
            _("Phase 3: Reconciled with ADVR (force mode)"),
            _(""),
            _("Remaining unreconciled lines: %(count)d") % {"count": remaining_lines},
        ]

        if remaining_lines > 0:
            result_lines.append(
                _("Note: Some lines could not be reconciled automatically.")
            )

        self.write(
            {
                "state": "done",
                "phase4_processed": 0,
                "result_message": "\n".join(result_lines),
            }
        )

        self._log("phase4", "complete", f"Wizard complete. {remaining_lines} remaining")

        _logger.info("Wizard complete. %d lines still unreconciled", remaining_lines)

        return self._return_wizard_action()

    def action_execute_all(self):
        """Execute all phases in sequence."""
        self.ensure_one()

        if self.state == "draft":
            self.action_analyze()

        if self.state == "analysis":
            self.action_phase1_unlink_partials()

        if self.state == "phase1":
            self.action_phase2_cleanup_orphan_krfrk()

        if self.state == "phase2":
            self.action_phase3_reconcile()

        if self.state == "phase3":
            self.action_phase4_finalize()

        if self.state == "done":
            self.write(
                {
                    "result_message": _(
                        "All phases completed successfully!\n\n"
                        "Summary:\n"
                        "- Phase 1: %(phase1)d partials unlinked\n"
                        "- Phase 2: %(phase2)d orphan KRFRK moves deleted\n"
                        "- Phase 3: %(phase3)d partners reconciled (with ADVR)\n\n"
                        "Please run calc_difference_invoice() for affected partners."
                    )
                    % {
                        "phase1": self.phase1_processed,
                        "phase2": self.phase2_processed,
                        "phase3": self.phase3_processed,
                    },
                }
            )

        return self._return_wizard_action()

    def action_reset(self):
        """Reset wizard to draft state."""
        self.ensure_one()
        self.write(
            {
                "state": "draft",
                "phase1_processed": 0,
                "phase2_processed": 0,
                "phase3_processed": 0,
                "phase4_processed": 0,
                "result_message": False,
            }
        )
        self.log_ids.unlink()
        return self._return_wizard_action()

    def _return_wizard_action(self):
        """Return action to keep wizard open after processing."""
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }


class CurrencyReconcileFixLog(models.TransientModel):
    _name = "currency.reconcile.fix.log"
    _description = "Currency Reconcile Fix Wizard Log"
    _order = "create_date desc"

    wizard_id = fields.Many2one(
        "currency.reconcile.fix.wizard",
        required=True,
        ondelete="cascade",
    )
    phase = fields.Selection(
        selection=[
            ("analysis", "Analysis"),
            ("phase1", "Phase 1: Unlink Partials"),
            ("phase2", "Phase 2: Cleanup KRFRK"),
            ("phase3", "Phase 3: Re-reconcile"),
            ("phase4", "Phase 4: Create Devir"),
        ],
        required=True,
    )
    action = fields.Char(required=True)
    details = fields.Text()
    partner_id = fields.Many2one("res.partner")
    amount = fields.Float()
