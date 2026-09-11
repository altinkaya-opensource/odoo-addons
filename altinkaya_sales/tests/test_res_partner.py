from odoo.tests.common import TransactionCase


class TestResPartnerSalespersonPropagation(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.new_salesperson = cls.env["res.users"].create(
            {
                "name": "New Company Salesperson",
                "login": "new_company_salesperson",
            }
        )
        cls.company = cls.env["res.partner"].create(
            {
                "name": "Salesperson Propagation Company",
                "is_company": True,
                "user_id": cls.env.ref("base.user_root").id,
            }
        )
        cls.children = cls.env["res.partner"].create(
            [
                {
                    "name": "Child with another salesperson",
                    "parent_id": cls.company.id,
                    "user_id": cls.env.ref("base.user_admin").id,
                },
                {
                    "name": "Archived child",
                    "parent_id": cls.company.id,
                    "user_id": cls.env.ref("base.user_admin").id,
                    "active": False,
                },
            ]
        )

    def test_company_salesperson_propagates_to_children(self):
        self.company.user_id = self.new_salesperson

        self.assertEqual(self.children.user_id, self.new_salesperson)

        self.company.user_id = False

        self.assertFalse(self.children.user_id)
