# Copyright 2023 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo import api, fields, models, _


class CreditControlPolicy(models.Model):
    _inherit = "credit.control.policy"

    def _get_move_lines_to_process(self, credit_control_run):
        """
        Filter out currency difference and opening AMLs
        """
        res = super()._get_move_lines_to_process(credit_control_run)
        return res.filtered(
            lambda a: not any(name in a.journal_id.code for name in ["KRFRK", "KFARK",])
        )
