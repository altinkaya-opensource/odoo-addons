from odoo import fields, models


class printing_printer_type(models.Model):
    _inherit = "printing.printer"
    type = fields.Char(string="Printer Type", size=64)
