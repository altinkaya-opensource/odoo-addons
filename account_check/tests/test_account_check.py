from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestAccountCheck(TransactionCase):
    def test_duplicate_third_check_raises_validation_error(self):
        journal = self.env["account.journal"].search(
            [("type", "=", "bank"), ("company_id", "=", self.env.company.id)],
            limit=1,
        )
        self.assertTrue(journal)

        bank = self.env["res.bank"].create({"name": "Duplicate Check Test Bank"})
        check_values = {
            "number": "DUPLICATE-CHECK-TEST",
            "type": "third_check",
            "owner_name": "Duplicate Check Test Owner",
            "bank_id": bank.id,
            "journal_id": journal.id,
        }
        self.env["account.check"].create(check_values)

        with self.assertRaisesRegex(
            ValidationError, "must be unique per Owner and Bank"
        ):
            self.env["account.check"].create(check_values)
