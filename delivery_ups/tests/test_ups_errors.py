from unittest.mock import MagicMock, patch

import requests

from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.delivery_ups.models.ups_request import UPSRequest

LOGGER = "odoo.addons.delivery_ups.models.ups_request"


def fake_response(status, body):
    response = MagicMock(status_code=status)
    response.json.return_value = body
    if status >= 400:
        response.raise_for_status.side_effect = requests.HTTPError(
            f"{status} Error", response=response
        )
    return response


@tagged("post_install", "-at_install")
class TestUPSErrors(TransactionCase):
    def _transit(self, response):
        token = fake_response(200, {"access_token": "token"})
        with patch(f"{LOGGER}.requests.post", side_effect=[token, response]):
            request = UPSRequest(
                client_id="id", client_secret="secret", delivery_carrier=MagicMock()
            )
            return request.get_transit_time({})

    def test_refusal_is_a_user_error_not_a_server_error(self):
        """UPS refusing the data we sent (400 with its own errors) reaches the
        user as a UserError but is not reported as a server error (Bugsink ODOO-5)."""
        body = {
            "response": {
                "errors": [
                    {"code": "111547", "message": "Weight is out of allowable range."}
                ]
            }
        }
        with (
            self.assertNoLogs(LOGGER, level="ERROR"),
            self.assertRaisesRegex(UserError, "111547"),
        ):
            self._transit(fake_response(400, body))

    def test_authorization_failure_is_still_an_error(self):
        body = {
            "response": {
                "errors": [
                    {"code": "250002", "message": "Invalid Authentication Information."}
                ]
            }
        }
        with self.assertLogs(LOGGER, level="ERROR"), self.assertRaises(UserError):
            self._transit(fake_response(401, body))
