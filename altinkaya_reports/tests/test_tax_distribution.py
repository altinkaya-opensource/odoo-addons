from odoo import Command
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestTaxDistribution(TransactionCase):
    def test_multiple_tax_accounts_and_distribution_factors(self):
        accounts = self.env["account.account"].create(
            [
                {
                    "name": "VAT test",
                    "code": "391.0TEST",
                    "account_type": "liability_current",
                },
                {
                    "name": "Deferred VAT test",
                    "code": "192.TEST",
                    "account_type": "asset_current",
                },
                {
                    "name": "Second VAT test",
                    "code": "391.0TEST2",
                    "account_type": "liability_current",
                },
            ]
        )
        tax = self.env["account.tax"].create(
            {"name": "Distribution test", "amount": 20}
        )
        for splits in (
            ((accounts[0], 100), (accounts[1], -100)),
            ((accounts[0], 50), (accounts[2], 50)),
        ):
            values = {}
            for field in (
                "invoice_repartition_line_ids",
                "refund_repartition_line_ids",
            ):
                values[field] = [
                    Command.clear(),
                    Command.create({"repartition_type": "base"}),
                ] + [
                    Command.create(
                        {
                            "repartition_type": "tax",
                            "account_id": account.id,
                            "factor_percent": factor,
                        }
                    )
                    for account, factor in splits
                ]
            tax.write(values)
            for move_type in ("out_invoice", "out_refund"):
                move = self.env["account.move"].new(
                    {
                        "move_type": move_type,
                        "currency_id": self.env.company.currency_id.id,
                    }
                )
                line = self.env["account.move.line"].new(
                    {
                        "move_id": move.id,
                        "account_id": accounts[0].id,
                        "display_type": "product",
                        "currency_id": self.env.company.currency_id.id,
                        "price_subtotal": 100,
                        "tax_ids": [Command.set(tax.ids)],
                    }
                )
                line._compute_kdv_amount()
                self.assertEqual(line.kdv_amount, 20)
                line.tax_ids = False
                line._compute_kdv_amount()
                self.assertEqual(line.kdv_amount, 0)
