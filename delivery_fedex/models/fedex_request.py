# Copyright 2025 Erol Develi (https://github.com/erlinberg)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).


import json
import logging

import requests

from odoo import _
from odoo.exceptions import UserError

# TODO: Find better way to handle URLs or use better names
FEDEX_API_URL = {
    "sandbox": "https://apis-sandbox.fedex.com",
    "prod": "https://apis.fedex.com",
}

FEDEX_SERVICES_BASE_URL = {
    "upload_document": {
        "sandbox": "https://documentapitest.prod.fedex.com/sandbox",
        "prod": "https://documentapi.prod.fedex.com",
    }
}

FEDEX_SERVICES_URL = {
    "rates": "rate/v1/rates/quotes",
    "auth": "oauth/token",
    "shipment": "ship/v1/shipments",
    "cancel": "ship/v1/shipments/cancel",
    "tracking": "track/v1/trackingnumbers",
    "upload_document": "documents/v1/etds/upload",
    "pickup_availability": "pickup/v1/pickups/availabilities",
    "pickup_request": "pickup/v1/pickups",
    "pickup_cancel": "pickup/v1/pickups/cancel",
}

REQUEST_TIMEOUT = 15  # seconds, used in requests

_logger = logging.getLogger(__name__)


class FedExRequest:
    def __init__(
        self,
        prod=False,
        client_id=None,
        client_secret=None,
        delivery_carrier=None,
    ):
        self.client_id = client_id
        self.client_secret = client_secret
        self.api_env = "prod" if prod else "sandbox"
        self.delivery_carrier = delivery_carrier
        self.access_token = self._get_oauth_key()

    def _get_service_url(self, service):
        return (
            (FEDEX_SERVICES_BASE_URL.get(service) or FEDEX_API_URL)[self.api_env]
            + "/"
            + FEDEX_SERVICES_URL[service]
        )

    def _check_for_errors(self, response):
        errors = None
        if response.get("errors"):
            errors = [(error["code"], error["message"]) for error in response["errors"]]

        return errors

    def _format_errors(self, response, error):
        if not response:
            return _("FedEx Error, %(error)s", error=str(error))

        error_string = "\n".join([e["message"] for e in response["errors"]])
        return _(
            "FedEx Error: %(error_string)s",
            error_string=error_string,
        )

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

        request_data = {}
        try:
            headers = {
                "X-locale": "en_US",
            }
            if auth:
                headers["Authorization"] = "Bearer " + self.access_token

            if content_type == "application/json":
                request_data["json"] = data
            elif content_type == "multipart/form-data":
                request_data["files"] = data
            else:
                request_data["data"] = data
                headers["Content-Type"] = content_type

            if request_type == "GET":
                res = requests.get(
                    url=url, headers=headers, timeout=REQUEST_TIMEOUT, **request_data
                )
            elif request_type == "POST":
                res = requests.post(
                    url=url, headers=headers, timeout=REQUEST_TIMEOUT, **request_data
                )
            elif request_type == "PUT":
                res = requests.put(
                    url=url, headers=headers, timeout=REQUEST_TIMEOUT, **request_data
                )
            else:
                raise UserError(
                    _("Unsupported request type, only use 'GET', 'POST' or 'PUT'")
                )
            result = res.json()

            # Remove 'attachment' to avoid logging raw binary data
            if content_type == "multipart/form-data":
                del request_data["files"]["attachment"]

            self.delivery_carrier.log_xml(
                "---Request:\n"
                + json.dumps(request_data, indent=4)
                + "\n\n---Response:\n"
                + json.dumps(result, indent=4),
                func=service_type,
            )
            res.raise_for_status()
        except requests.exceptions.Timeout as tmo:
            raise UserError(
                _(
                    "Timeout: the FedEx server did not reply within %(timeout)s",
                    timeout=REQUEST_TIMEOUT,
                ),
            ) from tmo
        except Exception as e:
            _logger.error(self._format_errors(result, e), exc_info=True)
            raise UserError(self._format_errors(result, e)) from e

        return res

    def get_rates(self, data):
        res = self._send_api_request("POST", "rates", data=data)
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

    def upload_document(self, data):
        res = self._send_api_request(
            "POST",
            "upload_document",
            data=data,
            content_type="multipart/form-data",
        )
        return res.json()

    def check_pickup_availability(self, data):
        """
        Check FedEx pickup availability for the given data.
        """
        res = self._send_api_request("POST", "pickup_availability", data=data)
        return res.json()

    def request_pickup(self, data):
        """
        Request a pickup from FedEx with the given data.
        """
        res = self._send_api_request("POST", "pickup_request", data=data)
        return res.json()

    def cancel_pickup(self, data):
        """
        Cancel a FedEx pickup with the given data.
        """
        res = self._send_api_request("PUT", "pickup_cancel", data=data)
        return res.json()
