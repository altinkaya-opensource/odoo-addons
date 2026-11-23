# Copyright 2026 Ahmet Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import models


class AccountPayment(models.Model):
    _inherit = "account.payment"

    def _prepare_move_line_default_vals(self, write_off_line_vals=None):
        """Convert the payment to company currency using the partner's
        currency rate field.

        The balances of a foreign-currency payment come from
        ``res.currency._convert``, which reads ``rate_type`` from the context.
        Without it the payment is booked at the currency's main rate field
        while the partner's invoices use ``property_rate_field``.
        """
        self.ensure_one()
        partner = self.partner_id
        if partner and partner.property_rate_field != "rate":
            self = self.with_context(rate_type=partner.property_rate_field)
        return super()._prepare_move_line_default_vals(
            write_off_line_vals=write_off_line_vals
        )
