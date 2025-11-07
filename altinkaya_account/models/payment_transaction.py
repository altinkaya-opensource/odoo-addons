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
from odoo import fields, models


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
        string="Installment Fee Invoice",
    )

    def action_cron_create_installment_fee_invoice(self, post_after_create=False):
        txs = self.search(
            [
                ("iyzico_installment_fee", ">", 0.1),
                ("installment_fee_invoiced", "=", False),
                ("payment_id.state", "=", "posted"),
            ]
        )
        try_currency = self.env.ref("base.TRY")
        installment_fee_account = self.env["account.account"].search(
            [("code", "=", "602.02")], limit=1
        )
        journal_id = self.env["account.journal"].search(
            [("code", "=", "VDFR")], limit=1
        )
        # 2ALTINKAYA-EFİNANS
        billing_point = self.env["account.billing.point"].browse(2)
        tax_id = self.env["account.tax"].search(
            [
                ("amount", "=", 20),
                ("type_tax_use", "=", "sale"),
                ("price_include", "=", False),
            ],
            limit=1,
        )
        unit_uom_id = self.env.ref("uom.product_uom_unit").id
        for tx in txs:
            commercial_partner = tx.partner_id.commercial_partner_id
            installment_fee = tx.iyzico_installment_fee
            fee_without_tax = installment_fee / 1.20
            invoice_vals = {
                "move_type": "out_invoice",
                "partner_id": commercial_partner.id,
                "journal_id": journal_id.id,
                "billing_point_id": billing_point.id,
                "installment_fee_tx_id": tx.id,
                "currency_id": try_currency.id,
                "invoice_line_ids": [
                    (
                        0,
                        0,
                        {
                            "name": f"Taksit Ücreti - İşlem Ref: {tx.reference}",
                            "quantity": 1,
                            "product_uom_id": unit_uom_id,
                            "price_unit": fee_without_tax,
                            "tax_ids": [(6, 0, [tax_id.id])],
                            "account_id": installment_fee_account.id,
                        },
                    )
                ],
            }
            invoice = self.env["account.move"].create(invoice_vals)
            tx.installment_fee_invoice_id = invoice.id
            tx.installment_fee_invoiced = True
            tx.invoiced_installment_fee = invoice.amount_total
            if post_after_create:
                invoice.action_post()
        return True
