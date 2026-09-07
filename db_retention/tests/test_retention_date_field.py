# Copyright 2026 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestRetentionDateField(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.log_model = cls.env["ir.model"]._get("ir.logging")
        cls.rule = cls.env["db.retention.rule"].create(
            {
                "name": "Retention date validation test",
                "model_id": cls.log_model.id,
                "date_field_id": cls.env["ir.model.fields"]
                ._get("ir.logging", "create_date")
                .id,
                "retention_days": 30,
                "active": False,
            }
        )

    def test_invalid_date_field_stops_before_search(self):
        for model_name, field_name in (
            ("ir.logging", "__last_update"),
            ("ir.logging", "name"),
            ("res.partner", "create_date"),
        ):
            with self.subTest(model=model_name, field=field_name):
                self.rule.date_field_id = self.env["ir.model.fields"]._get(
                    model_name, field_name
                )
                with (
                    patch.object(
                        type(self.env["ir.logging"]),
                        "search",
                        side_effect=AssertionError("Cleanup reached record search"),
                    ) as search,
                    self.assertRaises(ValidationError),
                ):
                    self.rule._clean()
                search.assert_not_called()

    def test_stored_date_keeps_retention_threshold(self):
        """Select only the old fixture; never execute a deletion in this test."""
        now = fields.Datetime.now()
        logs = self.env["ir.logging"].create(
            [
                {
                    "name": "Retention date test",
                    "type": "server",
                    "dbname": self.env.cr.dbname,
                    "level": "INFO",
                    "message": "Retention date test",
                    "path": __name__,
                    "func": "test_stored_date_keeps_retention_threshold",
                    "line": "0",
                }
                for _index in range(2)
            ]
        )
        for log, days in zip(logs, (60, 1), strict=True):
            # Set fixture timestamps through the ORM field; write() protects them.
            log._fields["create_date"].write(log, now - timedelta(days=days))
        self.rule.domain = repr([("id", "in", logs.ids)])

        matching = self.env["ir.logging"].search(self.rule._get_domain())

        self.assertEqual(matching, logs[0])
        self.assertEqual(logs.exists(), logs)
