# Copyright 2023 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo import api, fields, models


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    kdv_amount = fields.Monetary(
        default=0.0,
        currency_field="company_currency_id",
        string="Amount Total Currency",
        compute="_compute_kdv_amount",
        store=True,
        help="Total amount in company currency."
        " We use this field in account reporting.",
    )

    @api.depends(
        "move_id.invoice_date",
        "move_id.currency_id",
        "move_id.custom_rate",
        "move_id.move_type",
        "tax_ids",
        "price_subtotal",
    )
    def _compute_kdv_amount(self):
        for ail in self:
            ail.kdv_amount = 0.0
            for ail in self:
                currency_rate = ail.move_id.custom_rate
                kdv_amount = 0.0
                for tax in ail.tax_ids:
                    # We need to select tax_code based on invoice type
                    if ail.move_id.move_type in ["out_refund", "in_refund"]:
                        tax_code = tax.refund_repartition_line_ids.filtered(
                            lambda x: x.repartition_type == "tax"
                        ).account_id.code
                    else:
                        tax_code = tax.invoice_repartition_line_ids.filtered(
                            lambda x: x.repartition_type == "tax"
                        ).account_id.code

                    if tax_code and tax_code.startswith("191.0"):
                        kdv_amount -= ail.price_subtotal * tax.amount / 100
                    elif tax_code and tax_code.startswith("391.0"):
                        kdv_amount += ail.price_subtotal * tax.amount / 100

                # Convert to company currency
                if (
                    ail.currency_id != ail.company_currency_id
                    and currency_rate > 0.00001
                ):
                    kdv_amount = kdv_amount / currency_rate

                ail.kdv_amount = kdv_amount


"""
UPDATE
  account_move_line AS aml
SET
  kdv_amount = subquery.total_kdv
FROM
  (
    SELECT
      aml.id AS line_id,
      SUM(
        CASE
          WHEN aa.code LIKE '191.0%' THEN -1 * (aml.price_subtotal * at.amount / 100)
          WHEN aa.code LIKE '391.0%' THEN aml.price_subtotal * at.amount / 100
          ELSE 0
        END
      ) * CASE
          WHEN rc.id != 31 AND am.custom_rate > 0.00001 THEN 1 / am.custom_rate
          ELSE 1
        END AS total_kdv
    FROM
      account_move_line AS aml
      LEFT JOIN account_move_line_account_tax_rel AS amlatr ON aml.id = amlatr.account_move_line_id
      LEFT JOIN account_tax AS at ON at.id = amlatr.account_tax_id
      LEFT JOIN account_account AS aa ON at.invoice_repartition_line_ids.account_id = aa.id
      LEFT JOIN account_move AS am ON aml.move_id = am.id
      LEFT JOIN res_currency AS rc ON am.currency_id = rc.id
    WHERE
      aa.code LIKE '191.0%'
      OR aa.code LIKE '391.0%'
    GROUP BY
      aml.id,
      rc.id,
      am.custom_rate
  ) AS subquery
WHERE
  aml.id = subquery.line_id;
"""
