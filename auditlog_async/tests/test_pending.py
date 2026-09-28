# Copyright 2026 Altinkaya Enclosures
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json
from unittest.mock import patch

from odoo.tools import mute_logger

from odoo.addons.auditlog.tests.common import AuditLogRuleCommon


class TestAuditlogPending(AuditLogRuleCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner_model = cls.env.ref("base.model_res_partner")
        cls.rule = cls.create_rule(
            {
                "name": "partner",
                "model_id": cls.partner_model.id,
                "log_create": False,
                "log_write": True,
                "log_unlink": False,
                "log_type": "full",
            }
        )
        cls.rule.subscribe()
        cls.partner, cls.broken_partner = cls.env["res.partner"].create(
            [{"name": "Audited"}, {"name": "Broken"}]
        )
        # Keep a restored database's backlog out of the batch under test.
        cls.env.cr.execute(
            "UPDATE auditlog_pending SET state = 'done' WHERE state = 'pending'"
        )

    def _create_pending(self, partner, user_id):
        return self.env["auditlog.pending"].create(
            {
                "model_name": "res.partner",
                "res_id": partner.id,
                "method": "write",
                "user_id": user_id,
                "log_type": "full",
                "old_values_json": json.dumps({"name": "Before"}),
            }
        )

    def _search_logs(self, partner):
        return self.env["auditlog.log"].search(
            [
                ("model_id", "=", self.partner_model.id),
                ("res_id", "=", partner.id),
                ("method", "=", "write"),
            ]
        )

    def test_deleted_user_is_logged_without_user(self):
        """A user deleted after the change must not poison the batch."""
        self.env.cr.execute("SELECT MAX(id) + 1000 FROM res_users")
        deleted_user_id = self.env.cr.fetchone()[0]
        pending = self._create_pending(self.partner, deleted_user_id)

        self.env["auditlog.pending"].process_pending_batch()

        self.assertEqual(pending.state, "done")
        log = self._search_logs(self.partner)
        self.assertEqual(len(log), 1)
        self.assertFalse(log.user_id)
        self.assertEqual(log.line_ids.field_name, "name")

    def test_database_error_is_isolated_to_its_entry(self):
        """An aborted transaction must only fail its own pending entry."""
        broken = self._create_pending(self.broken_partner, self.env.uid)
        healthy = self._create_pending(self.partner, self.env.uid)
        rule_class = type(self.env["auditlog.rule"])
        create_logs = rule_class.create_logs

        def failing_create_logs(rule, uid, res_model, res_ids, *args):
            if res_ids == [self.broken_partner.id]:
                rule.env.cr.execute("SELECT 1 / 0")
            return create_logs(rule, uid, res_model, res_ids, *args)

        with (
            patch.object(rule_class, "create_logs", failing_create_logs),
            mute_logger("odoo.addons.auditlog_async.models.pending", "odoo.sql_db"),
        ):
            self.env["auditlog.pending"].process_pending_batch()
        self.env.flush_all()

        self.assertEqual(broken.state, "error")
        self.assertTrue(broken.error_message)
        self.assertEqual(broken.retry_count, 1)
        self.assertEqual(healthy.state, "done")
        self.assertEqual(len(self._search_logs(self.partner)), 1)
        self.assertFalse(self._search_logs(self.broken_partner))
