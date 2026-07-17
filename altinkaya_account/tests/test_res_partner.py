from odoo.tests.common import TransactionCase


class TestResPartnerExportAccounts(TransactionCase):
    def test_export_account_codes_on_create_and_country_write(self):
        turkey = self.env.ref("base.tr")
        united_states = self.env.ref("base.us")
        domestic_partner = self.env["res.partner"].create(
            {"name": "Domestic export code test", "country_id": turkey.id}
        )
        foreign_partner = self.env["res.partner"].create(
            {"name": "Foreign export code test", "country_id": False}
        )

        self.assertEqual(
            domestic_partner.z_receivable_export,
            f"120.{domestic_partner.ref.strip()}",
        )
        self.assertEqual(
            domestic_partner.z_payable_export,
            f"320.{domestic_partner.ref.strip()}",
        )
        self.assertFalse(foreign_partner.z_receivable_export)
        self.assertFalse(foreign_partner.z_payable_export)

        foreign_partner.country_id = united_states

        self.assertEqual(
            foreign_partner.z_receivable_export,
            f"120.Y{foreign_partner.ref.strip()}",
        )
        self.assertEqual(
            foreign_partner.z_payable_export,
            f"320.Y{foreign_partner.ref.strip()}",
        )
