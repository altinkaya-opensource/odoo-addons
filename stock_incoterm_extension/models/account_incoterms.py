from odoo import fields, models


class AccountIncoterms(models.Model):
    _inherit = "account.incoterms"

    destination_port = fields.Boolean(string="Requires destination port")
    transport_type = fields.Boolean(string="Requires transport type")
