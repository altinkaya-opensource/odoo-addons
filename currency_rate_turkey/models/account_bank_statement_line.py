# Copyright 2026 Ahmet Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import models


class AccountBankStatementLine(models.Model):
    _inherit = "account.bank.statement.line"

    def _get_amounts_with_currencies(self):
        """Convert the journal amount to company currency using the partner's
        currency rate field.

        For a foreign-currency bank journal the journal->company conversion
        goes through ``res.currency._convert``, which reads ``rate_type`` from
        the context. When the partner is only set at reconciliation time the
        move re-syncs without that context and falls back to the currency's
        main rate field. Inject ``property_rate_field`` here so the booked
        company amount always uses the same rate as the partner's invoices,
        regardless of when the partner was assigned.
        """
        self.ensure_one()
        partner = self.partner_id
        if partner and partner.property_rate_field != "rate":
            self = self.with_context(rate_type=partner.property_rate_field)
        return super()._get_amounts_with_currencies()
