# -*- encoding: utf-8 -*-
#
#Created on Jan 17, 2020
#
#@author: dogan
#
from odoo import models, fields, api


class ResCompany(models.Model):
    _inherit='res.company'


    hash_code = fields.Char('Hash Comm Code', help="Used in comm with ext services")
    tax_office_name = fields.Char('Tax Office', related='partner_id.tax_office_name')
