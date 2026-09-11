from odoo import fields
from odoo.tests.common import TransactionCase


class TestCRMLeadCurrency(TransactionCase):
    def test_expected_revenue_is_aggregated_in_usd(self):
        eur = self.env.ref("base.EUR")
        usd = self.env.ref("base.USD")
        lead = self.env["crm.lead"].create(
            {
                "name": "EUR opportunity",
                "type": "opportunity",
                "currency_id": eur.id,
                "expected_revenue": 1000.0,
            }
        )

        expected_usd = eur._convert(
            1000.0,
            usd,
            self.env.company,
            fields.Date.context_today(lead),
        )
        self.assertAlmostEqual(lead.expected_revenue_usd, expected_usd)

        groups = self.env["crm.lead"].read_group(
            [("id", "=", lead.id)],
            ["expected_revenue_usd"],
            ["stage_id"],
        )
        self.assertAlmostEqual(groups[0]["expected_revenue_usd"], expected_usd)

        lead.currency_id = usd
        self.assertEqual(lead.expected_revenue_usd, 1000.0)
