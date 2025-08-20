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

from odoo import models
from odoo.tools import float_compare

_logger = logging.getLogger(__name__)


class AccountAutoReconcile(models.AbstractModel):
    _name = "account.auto.reconcile"
    _description = "Account Auto Reconcile"

    def _cron_try_auto_reconcile_move_lines(self):
        invoices = self.env["account.move"].search(
            [
                ("state", "=", "posted"),
                (
                    "move_type",
                    "in",
                    ["out_invoice", "out_refund", "in_invoice", "in_refund"],
                ),
                ("payment_state", "=", "not_paid"),
            ],
            order="date desc",
            limit=100,  # Do not process too many invoices at once
        )
        for move in invoices:
            amount_residual = move.amount_residual
            invoice_currency = move.currency_id
            pay_term_lines = move.line_ids.filtered(
                lambda line: line.account_id.account_type
                in ("asset_receivable", "liability_payable")
            )
            domain = [
                ("account_id", "in", pay_term_lines.account_id.ids),
                ("parent_state", "=", "posted"),
                ("partner_id", "=", move.commercial_partner_id.id),
                ("reconciled", "=", False),
                "|",
                ("amount_residual", "!=", 0.0),
                ("amount_residual_currency", "!=", 0.0),
            ]

            if move.is_inbound():
                domain.append(("balance", "<", 0.0))
            else:
                domain.append(("balance", ">", 0.0))

            for line in self.env["account.move.line"].search(domain):
                if line.currency_id != invoice_currency:
                    continue

                # Use the amount_residual_currency to compare because
                # move and line are in the same currency.

                if (
                    float_compare(
                        abs(line.amount_residual_currency),
                        abs(amount_residual),
                        precision_rounding=0.1,
                    )
                    == 0
                ):
                    (line + pay_term_lines).reconcile()
                    _logger.debug("Auto-reconciled for %s invoice", move.name)
                    break
