# Copyright 2026 Yiğit Budak, Altinkaya Enclosures
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from unittest.mock import MagicMock, patch

import requests

from odoo.tests.common import TransactionCase

from odoo.addons.altinkaya_kardex.models.jmif_request import JmifRequest, _map_code

POST_PATH = "odoo.addons.altinkaya_kardex.models.jmif_request.requests.post"


class TestJmifRequest(TransactionCase):
    def setUp(self):
        super().setUp()
        self.req = JmifRequest("127.0.0.1", "5600", user="u", password="p")

    def test_payload_mapping(self):
        payload = self.req._prepare_payload(
            {
                "task_type": "get",
                "task_id": "a1",
                "address": "VLM-1",
                "carrier": "2",
                "pos_x": "5",
                "pos_y": "6",
                "qty": "42",
                "info1": "ORD-1",
                "info2": "PRT-7",
                "info3": "Resistor",
            }
        )
        self.assertEqual(
            payload,
            {
                "code": "2",
                "hostId": "a1",
                "addr": "VLM-1",
                "carrier": "2",
                "carrierNext": "0",
                "pos": "5",
                "depth": "6",
                "quant": "42",
                "order": "ORD-1",
                "part": "PRT-7",
                "desc": "Resistor",
                "x": "0",
                "y": "0",
                "height": "0",
                "mPos": "0",
                "mPos2": "0",
                "shortText": "",
            },
        )

    def test_code_mapping(self):
        self.assertEqual(_map_code("0"), "0")
        self.assertEqual(_map_code("104"), "-3")
        self.assertEqual(_map_code("107"), "-5")
        self.assertEqual(_map_code("101"), "-4")
        self.assertEqual(_map_code(""), "-2")

    def test_request_returns_operator_qty(self):
        """On success the operator-confirmed quant overrides the requested qty."""
        fake = MagicMock()
        fake.json.return_value = {"code": "0", "hostId": "a1", "quant": "25"}
        with patch(POST_PATH, return_value=fake):
            res = self.req.request_operation(
                {"task_type": "get", "task_id": "a1", "qty": "40"}
            )
        self.assertEqual(res, {"code": "0", "task_id": "a1", "qty": "25"})

    def test_connection_refused(self):
        with patch(POST_PATH, side_effect=requests.exceptions.ConnectionError):
            res = self.req.request_operation({"task_type": "get", "task_id": "a1"})
        self.assertEqual(res["code"], "-1")
