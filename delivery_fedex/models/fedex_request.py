import json

import requests

from odoo import _
from odoo.exceptions import UserError

FEDEX_API_URL = {
    "sandbox": "https://apis-sandbox.fedex.com",
    "prod": "https://apis.fedex.com",
}

FEDEX_SERVICES_URL = {
    "rates": "rate/v1/rates/quotes",
    "auth": "oauth/token",
    "shipment": "ship/v1/shipments",
}


class FedExRequest:
    def __init__(self, prod=False, client_id=None, client_secret=None):
        self.client_id = client_id
        self.client_secret = client_secret
        self.api_env = "prod" if prod else "sandbox"
        self.access_token = self._get_oauth_key()

    def _get_service_url(self, service):
        return FEDEX_API_URL[self.api_env] + "/" + FEDEX_SERVICES_URL[service]

    def _check_for_errors(self, response):
        errors = None
        if response.get("errors"):
            errors = [(error["code"], error["message"]) for error in response["errors"]]

        return errors

    def _format_errors(self, errors):
        formatted_result = ""
        for code, message in errors:
            formatted_result += f"Error {code}: {message}\n"

        return formatted_result

    def _get_oauth_key(self):
        res = self._send_api_request(
            request_type="POST",
            service_type="auth",
            content_type="application/x-www-form-urlencoded",
            auth=False,
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
        )
        auth_data = res.json()

        return auth_data.get("access_token")

    def _send_api_request(
        self,
        request_type,
        service_type,
        content_type="application/json",
        auth=True,
        data=None,
    ):
        if data is None:
            data = {}
        result = {}
        url = self._get_service_url(service_type)

        try:
            headers = {
                "Content-Type": content_type,
                "X-locale": "en_US",
            }
            if auth:
                headers["Authorization"] = "Bearer " + self.access_token

            if content_type == "application/json":
                data = json.dumps(data)

            if request_type == "GET":
                res = requests.get(url=url, headers=headers, data=data, timeout=60)
            elif request_type == "POST":
                res = requests.post(url=url, headers=headers, data=data, timeout=60)
            else:
                raise UserError(
                    _("Unsupported request type, please only use 'GET' or 'POST'")
                )
            result = res.json()
            res.raise_for_status()
        except requests.exceptions.Timeout as tmo:
            raise UserError(_("Timeout: the server did not reply within 60s")) from tmo
        except Exception as e:
            raise UserError(
                _("{error}\n{result}".format(error=e, result=result if result else ""))
            ) from e

        errors = self._check_for_errors(result)
        if errors:
            raise UserError(_(self._format_errors(errors)))
        return res

    def _format_rate_data(self, data):
        price = data["output"]["rateReplyDetails"][0]["ratedShipmentDetails"][1][
            "totalNetChargeWithDutiesAndTaxes"
        ]
        currency = data["output"]["rateReplyDetails"][0]["ratedShipmentDetails"][1][
            "currency"
        ]

        return {"price": price, "currency": currency}

    def get_rates(self, data):
        res = self._send_api_request("POST", "rates", data=data)
        return self._format_rate_data(res.json())

    def create_shipment(self, data):
        res = self._send_api_request("POST", "shipment", data=data)
        return res.json()
