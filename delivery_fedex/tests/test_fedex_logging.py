from unittest.mock import MagicMock, patch

from odoo.modules.neutralize import get_neutralization_queries
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.delivery_fedex.models.fedex_request import FedExRequest


@tagged("post_install", "-at_install")
class TestFedExLogging(TransactionCase):
    def _log(self, func):
        return self.env["ir.logging"].create(
            {
                "name": "delivery.carrier",
                "type": "server",
                "message": "{}",
                "path": "fedex",
                "func": func,
                "line": "1",
            }
        )

    @patch("odoo.addons.delivery_fedex.models.fedex_request.requests.post")
    def test_token_exchange_stays_out_of_the_log(self, post):
        post.return_value.json.return_value = {"access_token": "token"}
        carrier = MagicMock()

        request = FedExRequest(
            client_id="id", client_secret="secret", delivery_carrier=carrier
        )

        carrier.log_xml.assert_not_called()

        request.get_rates({"accountNumber": "1"})

        self.assertEqual(
            [call.kwargs["func"] for call in carrier.log_xml.call_args_list],
            ["fedex_rates_request", "fedex_rates_response"],
        )

    def test_neutralize_clears_only_the_token_exchange_logs(self):
        token_request = self._log("fedex_auth_request")
        token_response = self._log("fedex_auth_response")
        rate_request = self._log("fedex_rates_request")

        for query in get_neutralization_queries(["delivery_fedex"]):
            self.env.cr.execute(query)

        self.assertFalse(token_request.exists())
        self.assertFalse(token_response.exists())
        self.assertTrue(rate_request.exists())
