# Copyright 2026 Altinkaya Enclosures
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from unittest.mock import patch

from odoo import Command
from odoo.tests.common import TransactionCase, new_test_user


class TestCRMTeamRecompute(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(
            context=dict(cls.env.context, tracking_disable=True, no_reset_password=True)
        )
        cls.env["ir.config_parameter"].set_param("sales_team.membership_multi", False)
        cls.salesperson = new_test_user(
            cls.env, login="crm_memory_salesperson", password="CrmMemoryTest123!"
        )
        cls.new_member = new_test_user(
            cls.env, login="crm_memory_new_member", password="CrmMemoryTest123!"
        )
        cls.team = cls.env["crm.team"].create(
            {"name": "Existing team", "member_ids": [Command.link(cls.salesperson.id)]}
        )
        cls.other_team = cls.env["crm.team"].create(
            {"name": "Other team", "member_ids": [Command.link(cls.new_member.id)]}
        )
        cls.partners = cls.env["res.partner"].create(
            [
                {"name": "Existing customer", "user_id": cls.salesperson.id},
                {"name": "Transferred customer", "user_id": cls.new_member.id},
            ]
        )
        journal = cls.env["account.journal"].search(
            [("type", "=", "sale"), ("company_id", "=", cls.env.company.id)],
            limit=1,
        )
        cls.invoices = cls.env["account.move"].create(
            [
                {
                    "move_type": "out_invoice",
                    "journal_id": journal.id,
                    "partner_id": partner.id,
                }
                for partner in cls.partners
            ]
        )
        cls.env.flush_all()

    def test_adding_member_only_recomputes_changed_salespersons_invoices(self):
        computed_ids = set()
        model = type(self.invoices)
        original = model._compute_field_value

        def observe(records, field):
            if field.name == "team_id":
                computed_ids.update(records.ids)
            return original(records, field)

        with patch.object(model, "_compute_field_value", observe):
            self.team.write({"member_ids": [Command.link(self.new_member.id)]})
            self.env.flush_all()

        self.assertNotIn(self.invoices[0].id, computed_ids)
        self.assertIn(self.invoices[1].id, computed_ids)
        self.assertEqual(self.invoices.mapped("team_id"), self.team)
        self.assertFalse(self.other_team.member_ids)

    def test_saving_unchanged_members_does_not_recompute_invoice_teams(self):
        field = self.invoices._fields["team_id"]
        self.team.write({"member_ids": [Command.set(self.team.member_ids.ids)]})
        self.assertFalse(self.env.all.tocompute.get(field))

    def test_removing_member_and_changing_salesperson_update_invoice_team(self):
        self.team.write({"member_ids": [Command.unlink(self.salesperson.id)]})
        self.env.flush_all()
        self.assertFalse(self.invoices[0].team_id)

        self.partners[0].user_id = self.new_member
        self.env.flush_all()
        self.assertEqual(self.invoices[0].team_id, self.other_team)

    def test_invoice_team_compute_does_not_prefetch_unrelated_invoice_fields(self):
        read_fields = set()
        model = type(self.invoices)
        original_read = model._read

        def observe_read(records, names):
            if set(records.ids).intersection(self.invoices.ids):
                read_fields.update(names)
            return original_read(records, names)

        self.invoices.invalidate_recordset()
        self.env.add_to_compute(self.invoices._fields["team_id"], self.invoices)
        with patch.object(model, "_read", observe_read):
            self.invoices._recompute_recordset(["team_id"])

        self.assertIn("commercial_partner_id", read_fields)
        self.assertNotIn("narration", read_fields)
        self.assertEqual(self.invoices[0].team_id, self.team)
        self.assertEqual(self.invoices[1].team_id, self.other_team)
