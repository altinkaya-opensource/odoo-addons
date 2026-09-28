# Copyright 2026 Altinkaya Enclosures
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from unittest.mock import patch

from odoo import Command
from odoo.tests.common import new_test_user, tagged
from odoo.tools import mute_logger

from odoo.addons.auditlog.tests.common import AuditLogRuleCommon
from odoo.addons.base.models.res_users import name_boolean_group


@tagged("post_install", "-at_install")
class TestAuditlogBuffer(AuditLogRuleCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env["res.partner"].create({"name": "Initial", "phone": "111"})
        cls.user = new_test_user(cls.env, login="audited")
        cls.partner_model = cls.env.ref("base.model_res_partner")
        cls.create_rule(
            {
                "name": "partner",
                "model_id": cls.partner_model.id,
                "log_create": True,
                "log_write": True,
                "log_unlink": True,
                "log_type": "full",
                "capture_record": True,
            }
        ).subscribe()
        cls.create_rule(
            {
                "name": "partner category",
                "model_id": cls.env.ref("base.model_res_partner_category").id,
                "log_create": True,
                "log_type": "fast",
            }
        ).subscribe()
        cls.create_rule(
            {
                "name": "user",
                "model_id": cls.env.ref("base.model_res_users").id,
                "log_write": True,
                "log_type": "full",
            }
        ).subscribe()

    def _search_logs(self, record, method):
        return self.env["auditlog.log"].search(
            [
                ("model_model", "=", record._name),
                ("res_id", "in", record.ids),
                ("method", "=", method),
            ]
        )

    def _get_line_values(self, log):
        return {
            line.field_name: (line.old_value, line.new_value) for line in log.line_ids
        }

    def test_writes_are_logged_once_per_transaction(self):
        self.partner.name = "Second"
        self.partner.phone = "222"
        self.partner.name = "Final"
        self.assertFalse(self._search_logs(self.partner, "write"))

        self.env.cr.flush()

        log = self._search_logs(self.partner, "write")
        self.assertEqual(len(log), 1)
        self.assertEqual(log.user_id, self.env.user)
        self.assertEqual(
            self._get_line_values(log),
            {"name": ("Initial", "Final"), "phone": ("111", "222")},
        )

    def test_unchanged_values_are_not_logged(self):
        self.partner.write({"name": "Initial", "phone": "111"})
        self.env.cr.flush()
        self.assertFalse(self._search_logs(self.partner, "write"))

    def test_changes_through_a_parent_are_logged(self):
        self.partner.write({"child_ids": [Command.create({"name": "Child"})]})
        self.env.cr.flush()

        self.assertEqual(len(self._search_logs(self.partner.child_ids, "create")), 1)
        log = self._search_logs(self.partner, "write")
        self.assertEqual(log.line_ids.field_name, "child_ids")

    def test_rolled_back_changes_are_not_logged(self):
        with self.assertRaises(ValueError), self.env.cr.savepoint():
            self.partner.name = "Rolled back"
            raise ValueError("rollback")
        self.env.cr.flush()
        self.assertFalse(self._search_logs(self.partner, "write"))

    def test_unlink_logs_earlier_changes_and_the_record(self):
        partner = self.partner
        partner.phone = "222"
        partner.unlink()
        self.env.cr.flush()

        write_log = self._search_logs(partner, "write")
        self.assertEqual(self._get_line_values(write_log), {"phone": ("111", "222")})
        unlink_log = self._search_logs(partner, "unlink")
        self.assertEqual(unlink_log.name, "Initial")
        self.assertEqual(self._get_line_values(unlink_log)["name"], ("Initial", False))

    def test_fast_create_logs_given_fields_only(self):
        category = self.env["res.partner.category"].create({"name": "Tag"})
        self.env.cr.flush()
        log = self._search_logs(category, "create")
        self.assertEqual(self._get_line_values(log), {"name": (False, "Tag")})

    def test_group_checkbox_logs_groups_id(self):
        group = self.env.ref("base.group_partner_manager")
        self.assertNotIn(group, self.user.groups_id)
        self.user.write({name_boolean_group(group.id): True})
        self.env.cr.flush()
        log = self._search_logs(self.user, "write")
        self.assertEqual(log.line_ids.field_name, "groups_id")
        self.assertIn(str(group.id), log.line_ids.new_value)

    def test_logging_failure_keeps_the_change(self):
        rule_class = type(self.env["auditlog.rule"])
        create_logs = rule_class._create_buffered_logs

        def failing_create_logs(rule, logs):
            create_logs(rule, logs)
            rule.env.cr.execute("SELECT 1 / 0")

        self.partner.name = "Kept"
        with (
            patch.object(rule_class, "_create_buffered_logs", failing_create_logs),
            mute_logger("odoo.sql_db"),
            self.assertLogs("odoo.addons.auditlog_async.models.rule", level="ERROR"),
        ):
            self.env.cr.flush()

        self.assertFalse(self._search_logs(self.partner, "write"))
        self.env.cr.execute(
            "SELECT name FROM res_partner WHERE id = %s", [self.partner.id]
        )
        self.assertEqual(self.env.cr.fetchone()[0], "Kept")
