# Copyright 2025 Erol Develi (https://github.com/erlinberg)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).


import uuid
from datetime import datetime, timezone

import requests, base64

from odoo import _
from odoo.exceptions import UserError

_DHL_API_URL = {
    "sandbox": "https://express.api.dhl.com/mydhlapi/test",
    "prod": "https://express.api.dhl.com/mydhlapi",
}

_DHL_SERVICES_URL = {
    "rate": "rates",
    # "auth": "oauth/token",
    "shipment": "shipments",
    # "cancel": "ship/v1/shipments/cancel",
    "tracking": "tracking",
}

REQUEST_TIMEOUT = 20  # seconds, used in requests


class DHLRequest:
    def __init__(self, prod=False, api_key=None, api_secret=None):
        self.api_key = api_key
        self.api_secret = api_secret
        self.api_env = "prod" if prod else "sandbox"

    def _get_service_url(self, service):
        if service not in _DHL_SERVICES_URL:
            raise UserError(_("Unsupported DHL service: %s") % service)

        return _DHL_API_URL[self.api_env] + "/" + _DHL_SERVICES_URL[service]

    # TODO:
    # def _check_for_errors(self, response):
    #     errors = None
    #     if response.get("errors"):
    #         errors = [(error["code"], error["message"]) for error in response["errors"]]

    #     return errors

    # TODO:
    # def _format_errors(self, errors):
    #     formatted_result = ""
    #     for code, message in errors:
    #         formatted_result += f"Error {code}: {message}\n"

    #     return formatted_result

    def _send_api_request(
        self,
        request_type,
        service_type,
        content_type="application/json",
        data=None,
    ):
        if data is None:
            data = {}
        result = {}
        url = self._get_service_url(service_type)

        request_data = {}
        try:
            headers = {
                "Message-Reference": str(uuid.uuid4()),
                "Message-Reference-Date": datetime.now(timezone.utc)
                .isoformat(timespec="seconds")
                .replace("+00:00", "Z"),  # ISO 8601 in UTC
                "Plugin-Name": "odoo_delivery_dhl",
                "Plugin-Version": "16.0.1.0.0",
                "Shipping-System-Platform-Name": "Odoo",
                "Shipping-System-Platform-Version": "16.0",
                "Webstore-Platform-Name": "Odoo",
                "Webstore-Platform-Version": "16.0",
                "x-version": "2.12.0",
            }

            if content_type == "application/json":
                request_data["json"] = data
            else:
                request_data["data"] = data

            if request_type == "GET":
                res = requests.get(
                    url=url,
                    headers=headers,
                    timeout=REQUEST_TIMEOUT,
                    auth=(self.api_key, self.api_secret),
                    **request_data,
                )
            elif request_type == "POST":
                res = requests.post(
                    url=url,
                    headers=headers,
                    timeout=REQUEST_TIMEOUT,
                    auth=(self.api_key, self.api_secret),
                    **request_data,
                )
            else:
                raise UserError(_("Unsupported request type, only use 'GET', 'POST'"))
            result = res.json()
            res.raise_for_status()
        except requests.exceptions.Timeout as tmo:
            raise UserError(
                _(
                    "Timeout: the DHL servers did not reply within %(timeout)s seconds",
                    timeout=REQUEST_TIMEOUT,
                ),
            ) from tmo
        except Exception as e:
            raise UserError(
                "{error}\n{result}".format(error=e, result=result if result else "")
            ) from e

        # errors = self._check_for_errors(result)
        # if errors:
        #     raise UserError(_(self._format_errors(errors)))
        return res

    def get_rate(self, data):
        res = self._send_api_request("POST", "rate", data=data)
        return res.json()

    def create_shipment(self, data):
        res = self._send_api_request("POST", "shipment", data=data)
        return res.json()

    def cancel_shipment(self, data):
        res = self._send_api_request("PUT", "cancel", data=data)
        return res.json()

    def tracking_state_update(self, data):
        res = self._send_api_request("POST", "tracking", data=data)
        return res.json()
