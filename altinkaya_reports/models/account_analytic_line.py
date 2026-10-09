# Copyright 2026 Altinkaya Enclosures
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import api, fields, models


class AccountAnalyticLine(models.Model):
    _inherit = "account.analytic.line"

    amount_usd = fields.Float(
        string="Amount (USD)",
        compute="_compute_amount_usd",
        store=True,
        help="Analytic amount converted to USD at the entry date, keeping its sign.",
    )

    @api.depends("amount", "date", "currency_id", "company_id")
    def _compute_amount_usd(self):
        """Reuse each dated rate within the batch without rounding allocations."""
        usd = self.env.ref("base.USD")
        rates = {}
        for line in self.with_context(prefetch_fields=False):
            company = line.company_id or self.env.company
            currency = line.currency_id or company.currency_id
            date = line.date or fields.Date.context_today(line)
            key = (currency.id, company.id, date)
            if key not in rates:
                rates[key] = currency._convert(1.0, usd, company, date, round=False)
            line.amount_usd = line.amount * rates[key]
