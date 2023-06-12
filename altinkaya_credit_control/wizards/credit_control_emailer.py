# Copyright 2023 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo import _, api, models
from odoo.exceptions import UserError


class CreditControlEmailer(models.TransientModel):
    _inherit = "credit.control.emailer"

    @api.model
    def default_get(self, fields):
        super(CreditControlEmailer, self).default_get(fields)
        raise UserError(_("This method is restricted by Altinkaya Credit Control."))
