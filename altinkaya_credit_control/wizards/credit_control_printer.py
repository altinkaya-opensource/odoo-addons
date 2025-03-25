# Copyright 2023 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo import _, api, models
from odoo.exceptions import UserError


class CreditControlPrinter(models.TransientModel):
    _inherit = "credit.control.printer"

    @api.model
    def default_get(self, fields_list):
        super(CreditControlPrinter, self).default_get(fields_list)
        raise UserError(_("This method is restricted by Altinkaya Credit Control."))
