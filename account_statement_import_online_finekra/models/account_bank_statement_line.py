# Copyright 2024 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
import re

from odoo import api, fields, models
from odoo.tools import float_compare


class AccountBankStatementLine(models.Model):
    _inherit = "account.bank.statement.line"

    order_ids = fields.Many2many(
        "sale.order",
        "sale_order_bank_statement_line_rel",
        "statement_line_id",
        "order_id",
        string="Sale Orders",
    )

    @api.model_create_multi
    def create(self, vals_list):
        """
        Inherited to automatically bind orders to statement line
        :param vals:
        :return:
        """
        res = super().create(vals_list)
        order_ref_pattern = r"\b[A-Za-z]{2}\d{6,7}\b"
        for r in res:
            matched_refs = re.findall(order_ref_pattern, r.payment_ref)
            if not matched_refs:
                continue
            # Todo: this method could be multi as well
            orders = self.env["sale.order"].search(
                [
                    ("name", "in", matched_refs),
                    ("state", "in", ["draft", "sent"]),
                ]
            )
            if len(orders) != 1:
                continue

            if float_compare(orders.amount_total, res.amount, 2) != 0:
                continue

            commercial_partner = orders.mapped("partner_id.commercial_partner_id")

            # We can't create payment for multiple partners
            if len(commercial_partner) > 1:
                continue

            # Only work on positive amounts
            if r.amount < 0:
                continue

            # Update statement line parameters
            r.partner_id = commercial_partner.id
            reconcile_data_copy = r.reconcile_data_info.copy()
            for reconcile_line in reconcile_data_copy["data"]:
                if not reconcile_line["id"]:
                    reconcile_line["kind"] = "other"
                    reconcile_line["account_id"] = [
                        commercial_partner.property_account_receivable_id.id,
                        commercial_partner.property_account_receivable_id.display_name,
                    ]
                    reconcile_line["currency_id"] = (
                        commercial_partner.property_account_receivable_id.currency_id.id
                        or r.company_id.currency_id.id
                    )

                    # Set the manual reference for the reconciliation
                    reconcile_data_copy["manual_reference"] = reconcile_line[
                        "reference"
                    ]

            r.reconcile_data_info = reconcile_data_copy

            # Recompute amounts etc.
            r._onchange_manual_reconcile_vals()
            r.reconcile_bank_line()

            # Bind orders to statement line
            r.order_ids = [(6, 0, orders.ids)]

            # Update orders with payment
            orders.write(
                {
                    "payment_status": "done",
                    "payment_term_id": 23,  # Banka havalesi
                },
            )
            orders.with_context(bypass_risk=True).action_confirm()
        return res
