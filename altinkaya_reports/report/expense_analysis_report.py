from odoo import fields, models


class ExpenseAnalysisReport(models.Model):
    _name = "expense.analysis.report"
    _description = "Expense Analysis"
    _auto = False
    _order = "date desc"

    date = fields.Date(readonly=True)
    state = fields.Selection(
        [("draft", "Draft"), ("posted", "Posted"), ("cancel", "Cancelled")],
        readonly=True,
    )
    account_id = fields.Many2one("account.account", readonly=True)
    expense_item_id = fields.Many2one("expense.item", readonly=True)
    expense_unit_id = fields.Many2one("expense.unit", readonly=True)
    expense_type_id = fields.Many2one("expense.type", readonly=True)
    partner_id = fields.Many2one("res.partner", readonly=True)
    company_id = fields.Many2one("res.company", readonly=True)
    balance_tl = fields.Float(string="Amount (TL)", readonly=True)
    balance_usd = fields.Float(string="Amount (USD)", readonly=True)
    debit = fields.Float(readonly=True)
    credit = fields.Float(readonly=True)

    @property
    def _table_query(self):
        return f"{self._select()} {self._from()} {self._where()}"

    def _select(self):
        return """
            SELECT
                aml.id                                   AS id,
                aml.date                                 AS date,
                am.state                                 AS state,
                aml.account_id                           AS account_id,
                acc.expense_item_id                      AS expense_item_id,
                acc.expense_unit_id                      AS expense_unit_id,
                acc.expense_type_id                      AS expense_type_id,
                aml.partner_id                           AS partner_id,
                aml.company_id                           AS company_id,
                aml.balance                              AS balance_tl,
                aml.balance * COALESCE(am.usd_rate, 1.0) AS balance_usd,
                aml.debit                                AS debit,
                aml.credit                               AS credit
        """

    def _from(self):
        return """
            FROM account_move_line aml
            JOIN account_account acc ON acc.id = aml.account_id
            JOIN account_move am ON am.id = aml.move_id
        """

    def _where(self):
        return """
            WHERE aml.display_type NOT IN ('line_section', 'line_note')
              AND (acc.expense_item_id IS NOT NULL
                   OR acc.expense_unit_id IS NOT NULL
                   OR acc.expense_type_id IS NOT NULL)
        """
