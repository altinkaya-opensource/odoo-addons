from unittest.mock import MagicMock, patch

import requests

from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.delivery_dhl.models.dhl_request import DHLRequest

LOGGER = "odoo.addons.delivery_dhl.models.dhl_request"


def fake_response(status, body=None):
    response = MagicMock(status_code=status)
    if body is None:
        response.json.side_effect = ValueError("not JSON")
    else:
        response.json.return_value = body
    response.raise_for_status.side_effect = requests.HTTPError(
        f"{status} Error", response=response
    )
    return response


@tagged("post_install", "-at_install")
class TestDHLErrors(TransactionCase):
    def _rate(self, response):
        request = DHLRequest(
            api_key="key", api_secret="secret", delivery_carrier=MagicMock()
        )
        with patch(f"{LOGGER}.requests.post", return_value=response):
            return request.get_rate({"productCode": "H"})

    def test_refusal_is_a_user_error_not_a_server_error(self):
        """DHL refusing the shipment we asked about (400 with its own answer)
        reaches the user as a UserError but is not reported as a server error
        (Bugsink ODOO-9)."""
        body = {
            "title": "Bad request",
            "detail": "410105: Requested product(s) not available",
            "status": "400",
        }
        with (
            self.assertNoLogs(LOGGER, level="ERROR"),
            self.assertRaisesRegex(UserError, "410105"),
        ):
            self._rate(fake_response(400, body))

    def test_outage_page_keeps_its_status(self):
        with (
            self.assertLogs(LOGGER, level="ERROR"),
            self.assertRaisesRegex(UserError, "503"),
        ):
            self._rate(fake_response(503))
