# Copyright (C) 2025 Ahmet Yiğit Budak (https://github.com/yibudak)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class PaymentTransaction(models.Model):
    _inherit = "payment.transaction"

    invoiced_installment_fee = fields.Float(
        default=0.0,
    )
    installment_fee_invoiced = fields.Boolean(
        default=False,
    )
    installment_fee_invoice_id = fields.Many2one(
        "account.move",
    )

    def _create_installment_fee_invoice(
        self, invoice_configuration, post_after_create=False
    ):
        self.ensure_one()
        commercial_partner = self.partner_id.commercial_partner_id
        fee_without_tax = self.iyzico_installment_fee / 1.20
        invoice_vals = {
            "move_type": "out_invoice",
            "partner_id": commercial_partner.id,
            "journal_id": invoice_configuration["journal_id"],
            "billing_point_id": invoice_configuration["billing_point_id"],
            "installment_fee_tx_id": self.id,
            "currency_id": invoice_configuration["currency_id"],
            "invoice_line_ids": [
                (
                    0,
                    0,
                    {
                        "name": f"Taksit Ücreti - İşlem Ref: {self.reference}",
                        "quantity": 1,
                        "product_uom_id": invoice_configuration["unit_uom_id"],
                        "price_unit": fee_without_tax,
                        "tax_ids": [(6, 0, [invoice_configuration["tax_id"]])],
                        "account_id": invoice_configuration["account_id"],
                    },
                )
            ],
        }
        invoice = self.env["account.move"].create(invoice_vals)
        if post_after_create:
            invoice.action_post()
        self.write(
            {
                "installment_fee_invoice_id": invoice.id,
                "installment_fee_invoiced": True,
                "invoiced_installment_fee": invoice.amount_total,
            }
        )
        return invoice

    def action_cron_create_installment_fee_invoice(self, post_after_create=False):
        currency = self.env.ref("base.TRY")
        installment_fee_account = self.env["account.account"].search(
            [("code", "=", "602.02")], limit=1
        )
        journal = self.env["account.journal"].search([("code", "=", "VDFR")], limit=1)
        # 2ALTINKAYA-EFİNANS
        billing_point = self.env["account.billing.point"].browse(2).exists()
        tax = self.env["account.tax"].search(
            [
                ("amount", "=", 20),
                ("type_tax_use", "=", "sale"),
                ("price_include", "=", False),
            ],
            limit=1,
        )
        unit_uom = self.env.ref("uom.product_uom_unit")
        for record in (installment_fee_account, journal, billing_point, tax):
            record.ensure_one()
        invoice_configuration = {
            "currency_id": currency.id,
            "account_id": installment_fee_account.id,
            "journal_id": journal.id,
            "billing_point_id": billing_point.id,
            "tax_id": tax.id,
            "unit_uom_id": unit_uom.id,
        }
        txs = self.search(
            [
                ("iyzico_installment_fee", ">", 0.1),
                ("installment_fee_invoiced", "=", False),
                ("payment_id.state", "=", "posted"),
            ]
        )
        for tx in txs:
            try:
                with self.env.cr.savepoint():
                    tx._create_installment_fee_invoice(
                        invoice_configuration, post_after_create=post_after_create
                    )
            except Exception:  # pylint: disable=W0718
                commercial_partner = tx.partner_id.commercial_partner_id
                _logger.exception(
                    "Failed to create installment fee invoice for transaction "
                    "%s (%s), partner %s (%s); the transaction will be retried.",
                    tx.id,
                    tx.reference,
                    commercial_partner.id,
                    commercial_partner.display_name,
                )
        return True
