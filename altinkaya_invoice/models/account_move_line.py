from odoo import models, fields, api

class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    move_name = fields.Char(related='move_id.name', string='Move Number')
    move_ref = fields.Char(related='move_id.ref', string='Move Reference')
