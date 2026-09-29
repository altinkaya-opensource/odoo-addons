# Copyright 2026 Altinkaya Enclosures
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json

from odoo.tests.common import HttpCase, new_test_user, tagged

from odoo.addons.auditlog.tests.common import AuditLogRuleCommon


@tagged("post_install", "-at_install")
class TestAuditlogHttpContext(AuditLogRuleCommon, HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = new_test_user(
            cls.env,
            login="audit_http",
            groups="base.group_user,base.group_partner_manager",
        )
        cls.partner = cls.env["res.partner"].create({"name": "Before"})
        cls.create_rule(
            {
                "name": "partner",
                "model_id": cls.env.ref("base.model_res_partner").id,
                "log_write": True,
                "log_type": "fast",
            }
        ).subscribe()

    def test_log_keeps_the_request_that_made_the_change(self):
        self.authenticate("audit_http", "audit_http")
        url = "/web/dataset/call_kw/res.partner/write"
        params = {
            "model": "res.partner",
            "method": "write",
            "args": [self.partner.ids, {"name": "After"}],
            "kwargs": {},
        }
        response = self.url_open(
            url,
            data=json.dumps({"jsonrpc": "2.0", "params": params}),
            headers={"Content-Type": "application/json"},
        )
        self.assertNotIn("error", response.json())

        log = self.env["auditlog.log"].search(
            [("model_model", "=", "res.partner"), ("res_id", "=", self.partner.id)]
        )
        self.assertEqual(log.user_id, self.user)
        self.assertEqual(log.http_request_id.name, url)
        self.assertEqual(log.http_session_id.user_id, self.user)
