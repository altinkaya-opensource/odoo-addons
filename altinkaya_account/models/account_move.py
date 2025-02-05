# Copyright 2025 Ismail Çağan Yılmaz (https://github.com/milleniumkid)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import api, fields, models


class AccountMove(models.Model):
    _inherit = "account.move"

    total_balance = fields.Float(compute="_compute_partner_balance", store=False)

    def _compute_partner_balance(self):
        for move in self:
            partner = move.partner_id
            if partner.commercial_partner_id != partner:
                comm_partner = partner.commercial_partner_id
                balance = comm_partner.credit - comm_partner.debit
            else:
                balance = partner.credit - partner.debit
            move.total_balance = balance
