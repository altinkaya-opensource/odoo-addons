# -*- coding: utf-8 -*-

from odoo import api, fields, models, _


class printing_printer_type(models.Model):
    _inherit = 'printing.printer'
    type = fields.Char(string='Printer Type', size=64)


# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
