# Copyright 2022 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import models, fields


class AddressDistrict(models.Model):
    _inherit = "address.district"

    sendeo_code = fields.Integer(string='Sendeo District Code')
