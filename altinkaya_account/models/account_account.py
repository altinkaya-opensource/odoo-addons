from odoo import fields, models


class AccountAccount(models.Model):
    _inherit = "account.account"

    expense_item_id = fields.Many2one("expense.item", index=True)
    expense_unit_id = fields.Many2one("expense.unit", index=True)
    expense_type_id = fields.Many2one("expense.type", index=True)
