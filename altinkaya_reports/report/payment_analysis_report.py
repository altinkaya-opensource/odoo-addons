from odoo import fields, models


class PaymentAnalysisReport(models.Model):
    _name = "payment.analysis.report"
    _description = "Payment Analysis"
    _auto = False
    _order = "date desc"

    date = fields.Date(readonly=True)
    partner_id = fields.Many2one("res.partner", readonly=True)
    company_id = fields.Many2one("res.company", readonly=True)
    account_id = fields.Many2one("account.account", readonly=True)
    category = fields.Selection(
        [
            ("customer_collection", "Customer Collection"),
            ("supplier_payment", "Supplier Payment"),
            ("tax", "Tax"),
            ("personnel", "Personnel"),
            ("loan", "Loan"),
        ],
        readonly=True,
    )
    channel = fields.Selection(
        [
            ("cash", "Cash"),
            ("pos", "POS"),
            ("cheque", "Cheque"),
            ("bank", "Bank"),
            ("credit_card", "Credit Card"),
        ],
        readonly=True,
    )
    amount_tl = fields.Float(string="Amount (TL)", readonly=True)
    amount_usd = fields.Float(string="Amount (USD)", readonly=True)

    @property
    def _table_query(self):
        return r"""
            SELECT b.id, b.date, b.partner_id, b.company_id, b.account_id,
                   b.category, b.channel, b.amount_tl,
                   b.amount_tl * COALESCE(usd.rate, 0.0) AS amount_usd
            FROM (
                SELECT aml.id, aml.date, aml.partner_id, aml.company_id, aml.account_id,
                       'customer_collection' AS category,
                       CASE WHEN acc.code ~ '^108' THEN 'pos'
                            WHEN acc.code ~ '^101' THEN 'cheque'
                            ELSE 'cash' END AS channel,
                       aml.debit AS amount_tl
                FROM account_move_line aml
                JOIN account_account acc ON acc.id = aml.account_id
                WHERE aml.parent_state = 'posted' AND aml.debit > 0
                  AND acc.code ~ '^(100|101|102|108)'
                  AND EXISTS (
                      SELECT 1 FROM account_move_line c
                      JOIN account_account ca ON ca.id = c.account_id
                      WHERE c.move_id = aml.move_id AND ca.code ~ '^120'
                  )
                UNION ALL
                SELECT aml.id, aml.date, aml.partner_id, aml.company_id, aml.account_id,
                       'supplier_payment',
                       CASE WHEN acc.code ~ '^309($|\.)' THEN 'credit_card'
                            WHEN acc.code ~ '^(102|103)($|\.)' THEN 'bank'
                            WHEN acc.code ~ '^100($|\.)' THEN 'cash'
                            ELSE NULL END,
                       aml.credit
                FROM account_move_line aml
                JOIN account_account acc ON acc.id = aml.account_id
                WHERE aml.parent_state = 'posted' AND aml.credit > 0
                  AND acc.code ~ '^(100|102|103|309)($|\.)'
                  AND acc.code !~ '^(100\.D|102\.99|102\.X)'
                  AND EXISTS (
                      SELECT 1 FROM account_move_line c
                      JOIN account_account ca ON ca.id = c.account_id
                      WHERE c.move_id = aml.move_id AND ca.code ~ '^320'
                  )
                UNION ALL
                SELECT aml.id, aml.date, aml.partner_id, aml.company_id, aml.account_id,
                       'tax', NULL, aml.debit
                FROM account_move_line aml
                JOIN account_account acc ON acc.id = aml.account_id
                WHERE aml.parent_state = 'posted' AND aml.debit > 0
                  AND acc.code IN ('770.01.12','770.01.13','770.01.14','770.01.16',
                                   '770.01.17','770.50.06','770.50.20')
                UNION ALL
                SELECT aml.id, aml.date, aml.partner_id, aml.company_id, aml.account_id,
                       'personnel', NULL, aml.debit
                FROM account_move_line aml
                JOIN account_account acc ON acc.id = aml.account_id
                WHERE aml.parent_state = 'posted' AND aml.debit > 0
                  AND acc.code ~ '^(335|361)'
                UNION ALL
                SELECT aml.id, aml.date, aml.partner_id, aml.company_id, aml.account_id,
                       'loan', NULL, aml.debit
                FROM account_move_line aml
                JOIN account_account acc ON acc.id = aml.account_id
                WHERE aml.parent_state = 'posted' AND aml.debit > 0
                  AND acc.code ~ '^303'
            ) b
            LEFT JOIN LATERAL (
                SELECT r.rate FROM res_currency_rate r
                WHERE r.currency_id = (SELECT id FROM res_currency WHERE name = 'USD')
                  AND r.company_id = b.company_id
                  AND r.name <= b.date
                ORDER BY r.name DESC
                LIMIT 1
            ) usd ON TRUE
        """
