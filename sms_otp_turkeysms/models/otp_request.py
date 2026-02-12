# Copyright 2024 Ahmet Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
import logging
from datetime import datetime, timedelta

import requests

from odoo import fields, models

from odoo.addons.phone_validation.tools import phone_validation

_logger = logging.getLogger(__name__)
_SERVICE_URL = "https://turkeysms.com.tr/api/v3/otp/otp_get.php"


class OTPRequest(models.TransientModel):
    _name = "otp.request"
    _description = "OTP Request Transient Model"

    user_id = fields.Many2one(
        comodel_name="res.users",
    )
    user_lang = fields.Char(
        string="User Language",
    )
    one_time_password = fields.Integer()
    mobile_number = fields.Char(
        required=True,
    )
    expiry_date = fields.Datetime(
        default=lambda self: datetime.now() + timedelta(minutes=15),
        help="OTP will expire after this date."
        " It's set to 15 minutes from now by default.",
    )

    def send_otp(self):
        """Send OTP to the user's mobile number."""
        self.ensure_one()
        # Todo verify mobile number
        api_key = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("sms_otp_turkeysms.turkeysms_api_key")
        )
        if not api_key:
            return False
            # raise UserError(_("Please enter your TurkeySMS API key in the settings."))
        try:
            number_valid = phone_validation.phone_parse(self.mobile_number, "TR")
            if not number_valid:
                return False
        except Exception as exc:  # This means phone number is not valid
            _logger.error(exc)

        try:
            response = requests.get(
                _SERVICE_URL,
                timeout=10,
                params={
                    "api_key": api_key,
                    "mobile": self.mobile_number,
                    "lang": (
                        1 if self.user_lang == "tr_TR" else 0
                    ),  # 1 Turkish, 0 English, 2 Arabic
                    "response_type": "json",  # json or php array
                },
            )
            response.raise_for_status()
            response_json = response.json()
            if response_json["result"]:  # Returns True if successful
                self.one_time_password = response_json["otp_code"]
                return True
        except Exception as e:
            _logger.error(e)
            return False
