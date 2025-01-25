# Copyright 2025 Ismail Çağan Yılmaz (https://github.com/milleniumkid)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import api, fields, models


class AccountMove(models.Model):
    _inherit = "account.move"

    total_balance = fields.Float(readonly=True)

    @api.depends("partner_id")
    def partner_balance(self, partner_id):
        partner = self.env["res.partner"].browse(partner_id)
        if partner.commercial_partner_id != partner:
            comm_partner = partner.commercial_partner_id
            balance = comm_partner.credit - comm_partner.debit
        else:
            balance = partner.credit - partner.debit
        return balance

    @api.model
    def create(self, vals_list):
        if vals_list.get("partner_id"):
            vals_list["total_balance"] = self.partner_balance(vals_list["partner_id"])
        return super().create(vals_list)

    def write(self, vals):
        for invoice in self:
            if vals.get("partner_id"):
                partner_id = vals["partner_id"]
            else:
                partner_id = invoice.partner_id.id
            vals["total_balance"] = self.partner_balance(partner_id)
        return super().write(vals)
