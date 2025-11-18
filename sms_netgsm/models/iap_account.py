# Copyright (C) 2025 Ahmet Yiğit Budak (https://github.com/yibudak)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

from odoo import _, fields, models
from odoo.exceptions import UserError


class IapAccount(models.Model):
    _inherit = "iap.account"

    provider = fields.Selection(
        selection_add=[("sms_netgsm", "SMS Netgsm API")],
        ondelete={"sms_netgsm": "cascade"},
    )
    sms_netgsm_username = fields.Char(
        string="Netgsm Username",
        required=[("provider", "=", "sms_netgsm")],
        help="Username of your Netgsm account. (required)",
    )
    sms_netgsm_password = fields.Char(
        string="Netgsm Password",
        required=[("provider", "=", "sms_netgsm")],
        help="Password of your Netgsm account. (required)",
    )
    sms_netgsm_sms_header = fields.Char(
        string="Netgsm SMS Header",
        required=[("provider", "=", "sms_netgsm")],
        help="Sender ID (Title). If this field is empty,"
        " your first title registered in the system is used.",
    )
    sms_netgsm_iys_filter = fields.Selection(
        [
            ("0", "0 - Bilgilendirme (İYS kontrolü yapılmaz)"),
            ("11", "11 - Ticari (Bireysel, İYS kontrollü)"),
            ("12", "12 - Ticari (Tacir, İYS kontrollü)"),
        ],
        string="IYS Filter",
        default="0",
        help="Choose 'IYS Filter' to apply IYS filtering on your messages.",
    )

    def _get_service_from_provider(self):
        if self.provider == "sms_netgsm":
            return "sms"

    def get_netgsm_sms_balance(self):
        if not self or not (self.sms_netgsm_username and self.sms_netgsm_password):
            raise UserError(_("You need to save your Netgsm account first."))

        SmsAPI = self.env["sms.api"]
        balance = SmsAPI._get_balance_netgsm_sms_api(account=self)

        # Send a notification with the balance
        self.env["bus.bus"]._sendone(
            self.env.user.partner_id,
            "simple_notification",
            {
                "title": _("Netgsm SMS Balance"),
                "message": _(
                    "Your Netgsm SMS balance is: %(balance)s", balance=balance
                ),
            },
        )
        return True

    @property
    def _server_env_fields(self):
        res = super()._server_env_fields
        res.update(
            {
                "sms_netgsm_username": {},
                "sms_netgsm_password": {},
                "sms_netgsm_sms_header": {},
                "sms_netgsm_iys_filter": {},
            }
        )
        return res
