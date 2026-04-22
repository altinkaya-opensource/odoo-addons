# Copyright 2026 Altinkaya Enclosures, Ahmet Yigit Budak
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).


import json
import logging
import uuid

import requests

from odoo import _
from odoo.exceptions import UserError

UPS_API_URL = {
    "sandbox": "https://wwwcie.ups.com",
    "prod": "https://onlinetools.ups.com",
}

UPS_SERVICES_URL = {
    "auth": "/security/v1/oauth/token",
    "rate": "/api/rating/v2409/Rate",
    "shipment": "/api/shipments/v2409/ship",
    "void": "/api/shipments/v2409/void/cancel/%(shipmentId)s",
    "tracking": "/api/track/v1/details/%(inquiryNumber)s",
    "pickup_create": "/api/pickupcreation/v2409/pickup",
    "pickup_cancel": "/api/shipments/v2409/pickup/02",
}

REQUEST_TIMEOUT = 15  # seconds

_logger = logging.getLogger(__name__)


class UPSRequest:
    def __init__(
        self,
        prod=False,
        client_id=None,
        client_secret=None,
        account_number=None,
        delivery_carrier=None,
    ):
        self.client_id = client_id
        self.client_secret = client_secret
        self.account_number = account_number
        self.api_env = "prod" if prod else "sandbox"
        self.delivery_carrier = delivery_carrier
        self.access_token = self._get_oauth_key()

    def _get_service_url(self, service, url_params=None):
        if service not in UPS_SERVICES_URL:
            raise UserError(_("Unsupported UPS service: %s") % service)

        url = UPS_API_URL[self.api_env] + UPS_SERVICES_URL[service]
        if url_params is not None:
            url = url % url_params
        return url

    def _format_errors(self, response, error):
        if not response:
            return _("UPS Error: %(error)s", error=str(error))

        error_lines = []
        errors = (response.get("response") or {}).get("errors") or response.get(
            "errors", []
        )
        for e in errors:
            code = e.get("code", "")
            message = e.get("message", "")
            if code:
                error_lines.append(f"[{code}] {message}")
            else:
                error_lines.append(message)

        if not error_lines:
            return _("UPS Error: %(error)s", error=str(error))

        return _(
            "UPS Error:\n%(error_string)s",
            error_string="\n".join(error_lines),
        )

    def _get_oauth_key(self):
        """Request a bearer token using OAuth2 client credentials flow."""
        url = self._get_service_url("auth")
        try:
            res = requests.post(
                url=url,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "x-merchant-id": self.account_number or "",
                },
                data={"grant_type": "client_credentials"},
                auth=(self.client_id, self.client_secret),
                timeout=REQUEST_TIMEOUT,
            )
            result = res.json()

            if self.delivery_carrier:
                # Mask the token in logs to avoid leaking credentials.
                log_result = dict(result)
                if "access_token" in log_result:
                    log_result["access_token"] = "***"
                self.delivery_carrier.log_xml(
                    "---Request:\n"
                    + "grant_type=client_credentials"
                    + "\n\n---Response:\n"
                    + json.dumps(log_result, indent=4),
                    func="UPS - auth",
                )

            res.raise_for_status()
        except requests.exceptions.Timeout as tmo:
            raise UserError(
                _(
                    "Timeout: the UPS servers did not reply within %(timeout)s seconds",
                    timeout=REQUEST_TIMEOUT,
                )
            ) from tmo
        except Exception as e:
            _logger.error(self._format_errors(result, e), exc_info=True)
            raise UserError(self._format_errors(result, e)) from e

        return result.get("access_token")

    def _send_api_request(
        self,
        request_type,
        service_type,
        content_type="application/json",
        data=None,
        url_params=None,
        extra_headers=None,
    ):
        if data is None:
            data = {}
        result = {}
        url = self._get_service_url(service_type, url_params=url_params)

        request_data = {}
        try:
            headers = {
                "Authorization": "Bearer " + (self.access_token or ""),
                "transId": str(uuid.uuid4()),
                "transactionSrc": "altinkaya_odoo_ups",
            }
            if extra_headers:
                headers.update(extra_headers)

            if content_type == "application/json":
                request_data["json"] = data
            else:
                request_data["data"] = data
                headers["Content-Type"] = content_type

            if request_type == "GET":
                res = requests.get(
                    url=url,
                    headers=headers,
                    timeout=REQUEST_TIMEOUT,
                    **request_data,
                )
            elif request_type == "POST":
                res = requests.post(
                    url=url,
                    headers=headers,
                    timeout=REQUEST_TIMEOUT,
                    **request_data,
                )
            elif request_type == "DELETE":
                res = requests.delete(
                    url=url,
                    headers=headers,
                    timeout=REQUEST_TIMEOUT,
                    **request_data,
                )
            else:
                raise UserError(
                    _("Unsupported request type, only use 'GET', 'POST', 'DELETE'")
                )

            try:
                result = res.json()
            except ValueError:
                # Some successful void/cancel responses may have empty bodies.
                result = {}

            self.delivery_carrier.log_xml(
                "---Request:\n"
                + json.dumps(request_data, indent=4)
                + "\n\n---Response:\n"
                + json.dumps(result, indent=4),
                func=f"UPS - {service_type}",
            )
            res.raise_for_status()
        except requests.exceptions.Timeout as tmo:
            raise UserError(
                _(
                    "Timeout: the UPS servers did not reply within %(timeout)s seconds",
                    timeout=REQUEST_TIMEOUT,
                )
            ) from tmo
        except Exception as e:
            _logger.error(self._format_errors(result, e), exc_info=True)
            raise UserError(self._format_errors(result, e)) from e

        return res

    def get_rate(self, data):
        res = self._send_api_request("POST", "rate", data=data)
        return res.json()

    def create_shipment(self, data):
        res = self._send_api_request("POST", "shipment", data=data)
        return res.json()

    def cancel_shipment(self, shipment_id):
        res = self._send_api_request(
            "DELETE", "void", url_params={"shipmentId": shipment_id}
        )
        try:
            return res.json()
        except ValueError:
            return {}

    def tracking_state_update(self, inquiry_number):
        res = self._send_api_request(
            "GET", "tracking", url_params={"inquiryNumber": inquiry_number}
        )
        return res.json()

    def request_pickup(self, data):
        res = self._send_api_request("POST", "pickup_create", data=data)
        return res.json()

    def cancel_pickup(self, prn):
        """Cancel a pickup using its PRN (Pickup Request Number).
        UPS expects the PRN value in the `Prn` request header, not the body.
        """
        res = self._send_api_request(
            "DELETE",
            "pickup_cancel",
            extra_headers={"Prn": prn},
        )
        try:
            return res.json()
        except ValueError:
            return {}
