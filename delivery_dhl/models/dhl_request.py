# Copyright 2025 Erol Develi (https://github.com/erlinberg)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).


import json
import logging
import uuid
from datetime import UTC, datetime

import requests

from odoo import _
from odoo.exceptions import UserError

_DHL_API_URL = {
    "sandbox": "https://express.api.dhl.com/mydhlapi/test",
    "prod": "https://express.api.dhl.com/mydhlapi",
}

_DHL_SERVICES_URL = {
    "rate": "rates",
    "shipment": "shipments",
    "cancel": "pickups/%(dispatchConfirmationNumber)s",
    "tracking": "shipments/%(shipmentTrackingNumber)s/tracking",
}

REQUEST_TIMEOUT = 15  # seconds, used in requests

_logger = logging.getLogger(__name__)


class DHLRequest:
    def __init__(
        self, prod=False, api_key=None, api_secret=None, delivery_carrier=None
    ):
        self.api_key = api_key
        self.api_secret = api_secret
        self.api_env = "prod" if prod else "sandbox"

        self.delivery_carrier = delivery_carrier

    def _get_service_url(self, service):
        if service not in _DHL_SERVICES_URL:
            raise UserError(_("Unsupported DHL service: %s") % service)

        return _DHL_API_URL[self.api_env] + "/" + _DHL_SERVICES_URL[service]

    def _format_error(self, response, error=None):
        if not response:
            return _("DHL API Error: %(error)s", error=str(error))

        return _(
            "DHL API Error: %(title)s: %(message)s - %(detail)s",
            title=response.get("title", ""),
            message=response.get("message", ""),
            detail=response.get("detail", ""),
        )

    def _send_api_request(
        self,
        request_type,
        service_type,
        content_type="application/json",
        data=None,
        url_format_params=None,
    ):
        if data is None:
            data = {}
        result = {}
        url = self._get_service_url(service_type)

        if url_format_params is not None:
            url = url % url_format_params

        request_data = {}
        try:
            headers = {
                "Message-Reference": str(uuid.uuid4()),
                "Message-Reference-Date": datetime.now(UTC)
                .isoformat(timespec="seconds")
                .replace("+00:00", "Z"),  # ISO 8601 in UTC
                "Plugin-Name": "altinkaya_odoo_dhl",
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
            elif request_type == "DELETE":
                res = requests.delete(
                    url=url,
                    headers=headers,
                    timeout=REQUEST_TIMEOUT,
                    auth=(self.api_key, self.api_secret),
                    **request_data,
                )
            else:
                _logger.error(
                    "Unsupported request type: %s. Only 'GET', 'POST',"
                    " and 'DELETE' are supported.",
                    request_type,
                )
                raise UserError(
                    _("Unsupported request type, only use 'GET', 'POST', 'DELETE'")
                )
            result = res.json()
            self.delivery_carrier.log_xml(
                "---Request:\n"
                + json.dumps(request_data, indent=4)
                + "\n\n---Response:\n"
                + json.dumps(result, indent=4),
                func=f"DHL - {service_type}",
            )
            res.raise_for_status()
        except requests.exceptions.Timeout as tmo:
            _logger.error(
                "Timeout: the DHL servers did not reply within %s seconds",
                REQUEST_TIMEOUT,
            )
            raise UserError(
                _(
                    "Timeout: the DHL servers did not reply within %(timeout)s seconds",
                    timeout=REQUEST_TIMEOUT,
                ),
            ) from tmo
        except Exception as e:
            _logger.error(self._format_error(result, e), exc_info=True)
            raise UserError(self._format_error(result, e)) from e

        return res

    def get_rate(self, data):
        res = self._send_api_request("POST", "rate", data=data)
        return res.json()

    def create_shipment(self, data):
        res = self._send_api_request("POST", "shipment", data=data)
        return res.json()

    def cancel_pickup(self, data):
        res = self._send_api_request(
            "DELETE", "cancel", data=data, content_type=None, url_format_params=data
        )
        return res.status_code == 200, res.json()

    def tracking_state_update(self, data):
        res = self._send_api_request(
            "GET", "tracking", data=data, url_format_params=data
        )
        return res.json()
