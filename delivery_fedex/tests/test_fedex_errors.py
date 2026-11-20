from unittest.mock import MagicMock, patch

import requests

from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.delivery_fedex.models.fedex_request import FedExRequest

LOGGER = "odoo.addons.delivery_fedex.models.fedex_request"


def fake_response(status, body=None):
    response = MagicMock(status_code=status)
    if body is None:
        response.json.side_effect = ValueError("not JSON")
    else:
        response.json.return_value = body
    if status >= 400:
        response.raise_for_status.side_effect = requests.HTTPError(
            f"{status} Error", response=response
        )
    return response


@tagged("post_install", "-at_install")
class TestFedExErrors(TransactionCase):
    def _rates(self, response):
        token = fake_response(200, {"access_token": "token"})
        with patch(f"{LOGGER}.requests.post", side_effect=[token, response]):
            request = FedExRequest(
                client_id="id", client_secret="secret", delivery_carrier=MagicMock()
            )
            return request.get_rates({"accountNumber": "1"})

    def test_refusal_is_a_user_error_not_a_server_error(self):
        """FedEx refusing the data we sent (400 with its own errors) reaches the
        user as a UserError but is not reported as a server error (Bugsink ODOO-5)."""
        body = {
            "errors": [
                {
                    "code": "PACKAGE.WEIGHT.INVALID",
                    "message": "Package weight is missing or invalid.",
                }
            ]
        }
        with (
            self.assertNoLogs(LOGGER, level="ERROR"),
            self.assertRaisesRegex(UserError, "PACKAGE.WEIGHT.INVALID"),
        ):
            self._rates(fake_response(400, body))

    def test_outage_page_keeps_its_status(self):
        """An HTML outage page used to fail on JSON decoding and hide the HTTP
        status (Bugsink ODOO-80). It is still logged as an error."""
        with (
            self.assertLogs(LOGGER, level="ERROR"),
            self.assertRaisesRegex(UserError, "503"),
        ):
            self._rates(fake_response(503))
