# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import models


class AccountAutoReconcile(models.AbstractModel):
    _inherit = "account.auto.reconcile"

    def _get_payment_lines_domain(self, move, pay_term_account_ids):
        """Reserve Hepsiburada commissions for their API-referenced vendor bills."""
        return super()._get_payment_lines_domain(move, pay_term_account_ids) + [
            ("payment_id.is_hepsiburada_commission", "=", False),
        ]
