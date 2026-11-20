from unittest.mock import MagicMock, patch

from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestAutoReconcileSavepoint(TransactionCase):
    def test_failed_exact_match_keeps_the_transaction_usable(self):
        """A database error while reconciling one invoice must not abort the
        cron's transaction for every invoice after it (Bugsink ODOO-36)."""
        move = MagicMock()
        pay_term_lines = MagicMock()
        pay_term_lines.mapped.return_value = [100.0]
        payment_line = MagicMock(currency_id=move.currency_id)
        payment_line.amount_residual_currency = -100.0
        payment_line.__add__.return_value.reconcile.side_effect = lambda: (
            self.env.cr.execute("SELECT 1 / 0")
        )
        line_model = type(self.env["account.move.line"])

        with patch.object(line_model, "search", return_value=[payment_line]):
            reconciled = self.env["account.auto.reconcile"]._try_exact_match_reconcile(
                move, pay_term_lines
            )

        self.assertFalse(reconciled)
        self.env.cr.execute("SELECT 1")
        self.assertEqual(self.env.cr.fetchone(), (1,))
