from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestPartnerIndustrySearch(TransactionCase):
    def test_search_partners_by_industry_name(self):
        """A partner search on the industry name finds the partner (Bugsink ODOO-73)."""
        industry = self.env["res.partner.industry"].create(
            {"name": "Bugsink Test Industry", "code": "BT.01"}
        )
        partner = self.env["res.partner"].create(
            {"name": "Industry Search Partner", "industry_id": industry.id}
        )

        found = self.env["res.partner"].search(
            [("industry_id", "ilike", "Bugsink Test Industry")]
        )

        self.assertIn(partner, found)
