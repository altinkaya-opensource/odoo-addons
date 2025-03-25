# Copyright 2022 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

# Copyright 2024 Ismail Cagan Yilmaz (https://github.com/milleniumkid)
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

from odoo import _, fields, models
from odoo.exceptions import UserError


class IapAccount(models.Model):
    _inherit = "iap.account"

    provider = fields.Selection(
        selection_add=[("sms_verimor_http", "SMS Verimor API")],
        ondelete={"sms_verimor_http": "cascade"},
    )
    sms_verimor_http_username = fields.Char(
        string="Username",
        help="Username of your Verimor account. (required)",
    )
    sms_verimor_http_password = fields.Char(
        string="Password",
        help="Password of your Verimor account. (required)",
    )
    sms_verimor_http_sms_header = fields.Char(
        string="SMS Header",
        help="Sender ID (Title). If source_addr is empty,"
        " your first title registered in the system is used.",
    )

    def _get_service_from_provider(self):
        if self.provider == "sms_verimor_http":
            return "sms"

    def get_verimor_sms_balance(self):
        if not self or not (
            self.sms_verimor_http_username and self.sms_verimor_http_password
        ):
            raise UserError(_("You need to save your Verimor account first."))

        SmsAPI = self.env["sms.api"]
        balance = SmsAPI._get_balance_verimor_sms_api(account=self)
        raise UserError(balance)

    @property
    def _server_env_fields(self):
        res = super()._server_env_fields
        res.update(
            {
                "sms_verimor_http_username": {},
                "sms_verimor_http_password": {},
                "sms_verimor_http_sms_header": {},
            }
        )
        return res
