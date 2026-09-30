# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import fields
from odoo.tests.common import TransactionCase
from odoo.tools.convert import convert_file


class TestHepsiburadaCron(TransactionCase):
    def test_upgrade_preserves_disabled_crons_and_custom_schedules(self):
        """Upgrading legacy cron data must preserve the user's scheduling choices."""
        xmlids = self.env["ir.model.data"].search(
            [("module", "=", "hepsiburada_integration"), ("model", "=", "ir.cron")]
        )
        # Existing installations have unprotected external IDs.
        xmlids.write({"noupdate": False})
        crons = self.env["ir.cron"].browse(xmlids.mapped("res_id"))
        self.assertIn(self.env.ref("hepsiburada_integration.cron_import_orders"), crons)
        schedule = {
            "active": False,
            "interval_number": 3,
            "interval_type": "weeks",
            "nextcall": fields.Datetime.to_datetime("2030-01-02 03:04:05"),
        }
        crons.write(schedule)

        convert_file(
            self.env.cr,
            "hepsiburada_integration",
            "data/cron.xml",
            {},
            mode="update",
        )

        for cron in crons:
            with self.subTest(cron=cron.id):
                for name, value in schedule.items():
                    self.assertEqual(cron[name], value)

    def test_install_creates_active_order_import_cron(self):
        """New installations must still receive the default 15-minute schedule."""
        self.env.ref("hepsiburada_integration.cron_import_orders").unlink()

        convert_file(
            self.env.cr,
            "hepsiburada_integration",
            "data/cron.xml",
            {},
            mode="init",
        )

        cron = self.env.ref("hepsiburada_integration.cron_import_orders")
        self.assertTrue(cron.active)
        self.assertEqual(cron.interval_number, 15)
        self.assertEqual(cron.interval_type, "minutes")
        self.assertEqual(cron.code, "model._cron_import_orders()")
