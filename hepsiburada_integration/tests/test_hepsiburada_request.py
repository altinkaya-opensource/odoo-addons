# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from unittest.mock import Mock

from odoo.tests.common import TransactionCase

from ..models.hepsiburada_request import HepsiburadaRequest


class TestHepsiburadaRequest(TransactionCase):
    def setUp(self):
        super().setUp()
        self.client = HepsiburadaRequest("merchant", "user", "password")
        self.client._make_request = Mock(return_value=[])

    def test_package_page_size_is_clamped_to_ten(self):
        self.client.get_packages(offset=20, limit=50)

        params = self.client._make_request.call_args.kwargs["params"]
        self.assertEqual(params, {"offset": 20, "limit": 10})

    def test_question_api_uses_page_and_size_parameters(self):
        self.client.get_issues(current_page=3, page_size=50)

        params = self.client._make_request.call_args.kwargs["params"]
        self.assertEqual(params["page"], 3)
        self.assertEqual(params["size"], 25)
        self.assertNotIn("currentPage", params)

    def test_backend_pagination_uses_effective_page_size(self):
        fetch = Mock(
            side_effect=[
                [{"id": index} for index in range(10)],
                [{"id": index} for index in range(3)],
            ]
        )
        backend = self.env["hepsiburada.backend"]

        records = backend._fetch_all_packages(fetch, limit=10)

        self.assertEqual(len(records), 13)
        self.assertEqual(fetch.call_args_list[1].kwargs["offset"], 10)
