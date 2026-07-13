from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestPartnerOrgChartToggle(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env["res.partner"].create(
            {
                "name": "Organization Chart User",
                "email": "org-chart-user@example.com",
                "country_id": cls.env.company.country_id.id,
            }
        )
        cls.user = (
            cls.env["res.users"]
            .with_context(skip_password_policy=True, no_reset_password=True)
            .create(
                {
                    "name": cls.partner.name,
                    "login": "org-chart-user@example.com",
                    "partner_id": cls.partner.id,
                    "groups_id": [(6, 0, [cls.env.ref("base.group_portal").id])],
                }
            )
        )

    def test_toggle_archives_linked_user_before_partner(self):
        self.partner.toggle_active_from_org_chart()

        self.assertFalse(self.user.active)
        self.assertFalse(self.partner.active)

    def test_toggle_restores_partner_and_linked_user(self):
        self.partner.toggle_active_from_org_chart()
        self.partner.toggle_active_from_org_chart()

        self.assertTrue(self.partner.active)
        self.assertTrue(self.user.active)
