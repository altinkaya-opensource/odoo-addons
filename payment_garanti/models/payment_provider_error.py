# Copyright 2024 Ahmet Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo import api, fields, models


class PaymentProviderError(models.Model):
    _name = "payment.provider.error"
    _description = "Payment Provider Error"

    error_code = fields.Char(required=True)
    error_message = fields.Text(required=True)
    sys_error_message = fields.Text("System Error Message")
    log_id = fields.Many2one("ir.logging")
    modified_error_message = fields.Text(translate=True)
    full_message = fields.Text(
        store=True,
        compute="_compute_full_message",
    )

    @api.onchange("error_message")
    def _onchange_error_message(self):
        for error in self:
            error.modified_error_message = error.error_message

    @api.depends("error_code", "error_message")
    def _compute_full_message(self):
        for record in self:
            record.full_message = f"{record.error_code}: {record.error_message}"
