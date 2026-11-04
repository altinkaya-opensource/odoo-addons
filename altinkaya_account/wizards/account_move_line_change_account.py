from odoo import Command, _, fields, models
from odoo.exceptions import UserError

from ..models.account_move_line import CURRENCY_DIFFERENCE_JOURNAL_CODES


class AccountMoveLineChangeAccount(models.TransientModel):
    _name = "account.move.line.change.account"
    _description = "Change the Account of Journal Items"

    line_ids = fields.Many2many(
        "account.move.line",
        string="Journal Items",
        default=lambda self: self.env.context.get("active_ids"),
    )
    account_id = fields.Many2one(
        "account.account",
        string="New Account",
        required=True,
        domain=[("deprecated", "=", False)],
    )

    def action_change_account(self):
        """Move the selected journal items to the new account in one write.

        The write runs the checks Odoo applies to posted entries (lock dates,
        reconciliation, hashed entries, allowed journals) and recomputes the
        line currency from the new account, so the change is all or nothing.
        Only the check that ties account types to invoice types is skipped, so
        a receivable can be moved to a payable account and back.
        A posted line keeps its taxes: changing its account would otherwise
        make Odoo recompute them from the product or the new account, and a
        posted entry cannot drop a tax line.
        """
        self.ensure_one()
        # Items already on the new account are left as they are.
        lines = self.line_ids.filtered(lambda line: line.account_id != self.account_id)
        reconciled = lines.filtered(
            lambda line: line.matched_debit_ids or line.matched_credit_ids
        )
        if reconciled:
            raise UserError(
                _(
                    "Unreconcile these entries before changing their account:\n"
                    "%(moves)s",
                    moves="\n".join(reconciled.move_id.mapped("name")),
                )
            )
        # An invoice keeps all its lines in its own currency; a foreign-currency
        # account would relabel the amounts. Currency-difference documents are
        # TRY by design and keep a zero foreign amount.
        account_currency = self.account_id.currency_id
        mismatched = lines.filtered(
            lambda line: (
                account_currency
                and line.move_id.is_invoice(include_receipts=True)
                and line.journal_id.code not in CURRENCY_DIFFERENCE_JOURNAL_CODES
                and line.move_id.currency_id != account_currency
            )
        )
        if mismatched:
            raise UserError(
                _(
                    "%(account)s is kept in %(currency)s, but these invoices are "
                    "in another currency:\n%(moves)s",
                    account=self.account_id.display_name,
                    currency=account_currency.name,
                    moves="\n".join(mismatched.move_id.mapped("name")),
                )
            )
        lines = lines.with_context(skip_payable_receivable_check=True)
        # Changing the account of a product line makes Odoo recompute its
        # taxes, and a posted entry cannot lose a tax line. Keep the taxes the
        # posted lines already have, so the same write only moves them.
        for line in lines.filtered(lambda line: line.move_id.state == "posted"):
            line.write(
                {
                    "account_id": self.account_id.id,
                    "tax_ids": [Command.set(line.tax_ids.ids)],
                }
            )
        draft_lines = lines.filtered(lambda line: line.move_id.state != "posted")
        if draft_lines:
            draft_lines.write({"account_id": self.account_id.id})
        return {"type": "ir.actions.act_window_close"}
