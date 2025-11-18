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


from base64 import b64encode

import requests
from lxml import etree
from lxml.builder import E

from odoo import api, models
from odoo.exceptions import ValidationError

NETGSM_SEND_SMS_ENDPOINT = "https://api.netgsm.com.tr/sms/rest/v2/send"
NETGSM_GET_BALANCE_ENDPOINT = "https://api.netgsm.com.tr/balance"


class SmsApi(models.AbstractModel):
    _inherit = "sms.api"

    def _get_auth_header_netgsm(self, account):
        auth_str = f"{account.sms_netgsm_username}:{account.sms_netgsm_password}"
        return {"Authorization": f"Basic {b64encode(auth_str.encode()).decode()}"}

    def _prepare_netgsm_sms_params(self, account, number, message):
        return {
            "encoding": "TR",
            "iysfilter": account.sms_netgsm_iys_filter,
            "msgheader": account.sms_netgsm_sms_header,
            "messages": [{"msg": message, "no": number}],
        }

    def _send_sms_with_netgsm(self, account, number, message):
        r = requests.post(
            NETGSM_SEND_SMS_ENDPOINT,
            json=self._prepare_netgsm_sms_params(account, number, message),
            headers={
                "Content-Type": "application/json",
                **self._get_auth_header_netgsm(account),
            },
            timeout=30,
        )
        response = r.text
        if r.status_code != 200:
            raise ValidationError(response)

        return response

    def _get_balance_netgsm_sms_api(self, account):
        xml_element = E.mainbody(
            E.header(
                E.usercode(account.sms_netgsm_username),
                E.password(account.sms_netgsm_password),
                E.stip("2"),  # 2: get balance
                E.view("1"),  # 1: xml response
            )
        )
        xml_data = etree.tostring(xml_element, xml_declaration=True, encoding="utf-8")
        headers = {"Content-Type": "text/xml"}
        response = requests.post(
            NETGSM_GET_BALANCE_ENDPOINT,
            data=xml_data,
            headers=headers,
            timeout=30,
        )
        response = response.text
        # Load and parse XML response
        xml_response = etree.fromstring(response.encode())
        balance = xml_response.findtext(".//balance")

        if balance is None:
            raise ValidationError(response)

        return balance

    @api.model
    def _send_sms(self, numbers, message):
        account = self.env["iap.account"].get("sms")
        if account.provider == "sms_netgsm":
            self._send_sms_with_netgsm(account, numbers, message)
        else:
            return super()._send_sms(numbers, message)

    @api.model
    def _send_sms_batch(self, messages):
        # TODO: this is not the most efficient way to send SMS in batch.
        # netgsm API supports sending multiple messages in a single request.
        # but it works for now.
        """Send SMS messages in batch using Netgsm HTTP API"""
        account = self.env["iap.account"].get("sms")
        if account.provider != "sms_netgsm":
            return super()._send_sms_batch(messages)

        result = []
        for message in messages:
            try:
                self._send_sms_with_netgsm(
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
