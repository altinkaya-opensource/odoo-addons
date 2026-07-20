# Copyright 2026 Altinkaya Enclosures
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests.common import TransactionCase


class TestAuditlogFields(TransactionCase):
    def test_binary_fields_excluded(self):
        """Binary fields must never be read back for audit logging."""
        rule_model = self.env["auditlog.rule"]
        partner_model = self.env["res.partner"]
        fields_list = rule_model.get_auditlog_fields(partner_model)
        self.assertIn("name", fields_list)
        binary_fields = [
            fname
            for fname in fields_list
            if partner_model._fields[fname].type == "binary"
        ]
        self.assertFalse(
            binary_fields, f"Binary fields leaked into auditlog read: {binary_fields}"
        )
