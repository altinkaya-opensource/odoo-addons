from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, new_test_user


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

    def test_create_does_not_reuse_an_existing_commercial_ref(self):
        turkey = self.env.ref("base.tr")
        original = self.env["res.partner"].create(
            {"name": "Original commercial partner", "country_id": turkey.id}
        )
        duplicate = self.env["res.partner"].create(
            {
                "name": "Must not reuse original ref",
                "country_id": turkey.id,
                "ref": original.ref,
            }
        )
        self.assertTrue(duplicate.ref)
        self.assertNotEqual(duplicate.ref, original.ref)
        self.assertNotEqual(duplicate.z_receivable_export, original.z_receivable_export)
        self.assertEqual(duplicate.z_receivable_export, f"120.{duplicate.ref.strip()}")

    def test_portal_template_user_copy_gets_unique_ref_and_export_codes(self):
        """Storefront signup copies the portal template user via _inherits."""
        template_user_id = int(
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("base.template_portal_user_id")
        )
        template_user = self.env["res.users"].browse(template_user_id)
        self.assertTrue(template_user.exists())

        united_states = self.env.ref("base.us")
        template_partner = template_user.partner_id
        template_partner.write(
            {
                "ref": "92997",
                "country_id": united_states.id,
                "z_receivable_export": "120.Y92997",
                "z_payable_export": "320.Y92997",
            }
        )

        user = template_user.with_context(no_reset_password=True).copy(
            {
                "name": "Storefront signup unique ref",
                "login": "signup-unique-ref@example.com",
                "email": "signup-unique-ref@example.com",
                "active": True,
            }
        )
        partner = user.partner_id
        self.assertTrue(partner.ref)
        self.assertNotEqual(partner.ref, "92997")
        self.assertNotEqual(partner.z_receivable_export, "120.Y92997")
        self.assertEqual(partner.z_receivable_export, f"120.Y{partner.ref.strip()}")
        self.assertEqual(partner.z_payable_export, f"320.Y{partner.ref.strip()}")


class TestPaymentTermAccess(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        groups = (
            "base.group_partner_manager,sales_team.group_sale_salesman,"
            "account.group_account_invoice"
        )
        cls.salesman = new_test_user(
            cls.env, login="payment_term_salesman", groups=groups
        )
        cls.risk_manager = new_test_user(
            cls.env,
            login="payment_term_risk_manager",
            groups=f"{groups},account_financial_risk.group_account_financial_risk_manager",
        )
        cls.cash_term = cls.env["account.payment.term"].create({"name": "Cash test"})
        cls.credit_term = cls.env["account.payment.term"].create(
            {"name": "Credit test"}
        )
        cls.company = cls.env["res.partner"].create(
            {
                "name": "Payment term access company",
                "is_company": True,
                "property_payment_term_id": cls.cash_term.id,
            }
        )

    def test_only_risk_manager_sets_payment_term(self):
        partners = self.env["res.partner"].with_user(self.salesman)
        company = self.company.with_user(self.salesman)
        with self.assertRaises(AccessError):
            company.property_payment_term_id = self.credit_term
        with self.assertRaises(AccessError):
            partners.create(
                {
                    "name": "Payment term forged on create",
                    "property_payment_term_id": self.credit_term.id,
                }
            )

        # Commercial field sync to contacts still works for sales.
        contact = partners.create(
            {"name": "Payment term contact", "parent_id": company.id}
        )
        self.assertEqual(contact.property_payment_term_id, self.cash_term)
        company.company_registry = "PAYMENT-TERM-TEST"
        self.assertEqual(contact.company_registry, "PAYMENT-TERM-TEST")

        manager_company = self.company.with_user(self.risk_manager)
        manager_company.property_payment_term_id = self.credit_term
        self.assertEqual(self.company.property_payment_term_id, self.credit_term)
        self.assertEqual(contact.property_payment_term_id, self.credit_term)
