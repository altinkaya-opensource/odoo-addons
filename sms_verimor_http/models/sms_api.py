# Copyright 2022 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

# Copyright 2024 Ismail Cagan Yilmaz (https://github.com/milleniumkid)
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).


import requests

from odoo import api, models
from odoo.exceptions import ValidationError

VERIMOR_SEND_SMS_ENDPOINT = "http://sms.verimor.com.tr/v2/send.json"
VERIMOR_GET_BALANCE_ENDPOINT = "http://sms.verimor.com.tr/v2/balance"


class SmsApi(models.AbstractModel):
    _inherit = "sms.api"

    def _prepare_verimor_http_params(self, account, number, message):
        return {
            "username": account.sms_verimor_http_username,
            "password": account.sms_verimor_http_password,
            "source_addr": account.sms_verimor_http_sms_header,
            "messages": [{"msg": message, "dest": number}],
        }

    def _send_sms_with_verimor_http(self, account, number, message):
        r = requests.post(
            VERIMOR_SEND_SMS_ENDPOINT,
            json=self._prepare_verimor_http_params(account, number, message),
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        response = r.text
        if r.status_code != 200:
            raise ValidationError(response)

        return response

    def _get_balance_verimor_sms_api(self, account):
        r = requests.get(
            VERIMOR_GET_BALANCE_ENDPOINT,
            params={
                "username": account.sms_verimor_http_username,
                "password": account.sms_verimor_http_password,
            },
            timeout=10,
        )
        response = r.text
        if r.status_code != 200:
            raise ValidationError(response)
        return response

    @api.model
    def _send_sms(self, numbers, message):
        account = self.env["iap.account"].get("sms")
        if account.provider == "sms_verimor_http":
            self._send_sms_with_verimor_http(account, numbers, message)
        else:
            return super()._send_sms(numbers, message)

    @api.model
    def _send_sms_batch(self, messages):
        """Send SMS messages in batch using Verimor HTTP API"""
        account = self.env["iap.account"].get("sms")
        if account.provider != "sms_verimor_http":
            return super()._send_sms_batch(messages)

        result = []
        for message in messages:
            try:
                self._send_sms_with_verimor_http(
                    account, message["number"], message["content"]
                )
                result.append(
                    {
                        "res_id": message["res_id"],
                        "state": "success",
                    }
                )
            except ValidationError as e:
                result.append(
                    {
                        "res_id": message["res_id"],
                        "state": str(e),
                    }
                )

        return result
