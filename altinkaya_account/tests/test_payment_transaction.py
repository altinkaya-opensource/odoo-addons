from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase

from ..models import payment_transaction


class TestInstallmentFeeInvoiceCron(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        provider = cls.env.ref("payment_iyzico_altinkaya.payment_provider_iyzico")
        currency = cls.env.ref("base.TRY")
        partner = cls.env.user.partner_id
        cls.transactions = cls.env["payment.transaction"]
        for reference in ("FEE-BEFORE", "FEE-INVALID", "FEE-AFTER"):
            cls.transactions |= cls.env["payment.transaction"].create(
                {
                    "provider_id": provider.id,
                    "reference": reference,
                    "amount": 120.0,
                    "currency_id": currency.id,
                    "operation": "online_redirect",
                    "partner_id": partner.id,
                    "iyzico_installment_fee": 120.0,
                }
            )

    def test_failed_transaction_does_not_rollback_other_invoices(self):
        failed_tx = self.transactions.filtered(lambda tx: tx.reference == "FEE-INVALID")

        def create_installment_fee_invoice(
            tx, invoice_configuration, post_after_create=False
        ):
            tx.write(
                {
                    "installment_fee_invoiced": True,
                    "invoiced_installment_fee": tx.iyzico_installment_fee,
                }
            )
            if tx == failed_tx:
                raise UserError(self.env._("Partner tax office is missing"))
            return self.env["account.move"]

        with (
            patch.object(
                payment_transaction.PaymentTransaction,
                "search",
                return_value=self.transactions,
            ),
            patch.object(
                payment_transaction.PaymentTransaction,
                "_create_installment_fee_invoice",
                new=create_installment_fee_invoice,
            ),
            self.assertLogs(payment_transaction._logger.name, level="ERROR") as logs,
        ):
            result = self.env[
                "payment.transaction"
            ].action_cron_create_installment_fee_invoice(post_after_create=True)

        successful_txs = self.transactions - failed_tx
        self.assertTrue(result)
        self.assertTrue(all(successful_txs.mapped("installment_fee_invoiced")))
        self.assertEqual(
            successful_txs.mapped("invoiced_installment_fee"), [120.0, 120.0]
        )
        self.assertFalse(failed_tx.installment_fee_invoiced)
        self.assertEqual(failed_tx.invoiced_installment_fee, 0.0)
        self.assertIn(str(failed_tx.id), logs.output[0])
        self.assertIn(failed_tx.reference, logs.output[0])
