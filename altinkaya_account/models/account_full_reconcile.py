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
from odoo import models


class AccountFullReconcile(models.Model):
    _inherit = "account.full.reconcile"

    def get_report_data(self):
        """Returns report dictionary for currency difference report for reconcilation"""

        query = """SELECT AML.DATE AS DATE,
        CASE
            WHEN INV.SUPPLIER_INVOICE_NUMBER IS NOT NULL
            THEN AJ.NAME->>'en_US' || ' ' || INV.SUPPLIER_INVOICE_NUMBER
            WHEN INV.NUMBER IS NOT NULL
            THEN AJ.NAME->>'en_US' || ' ' || INV.NUMBER
            ELSE AJ.NAME->>'en_US'
        END AS DESCRIPTION,
        CASE
            WHEN (SUM(AML.DEBIT) - SUM(AML.CREDIT)) > 0
            THEN ROUND((SUM(AML.DEBIT) - SUM(AML.CREDIT)),2)
            ELSE 0.00
        END AS DEBIT,
        CASE
            WHEN SUM(AML.DEBIT) - SUM(AML.CREDIT) < 0
            THEN -1 * ROUND((SUM(AML.DEBIT) - SUM(AML.CREDIT)),2)
            ELSE 0.00
        END AS CREDIT,
        CASE
            WHEN ABS(SUM (AML.AMOUNT_CURRENCY)) > 0
            THEN ROUND(ABS(SUM(AML.DEBIT) - SUM(AML.CREDIT)) /
            ABS(SUM (AML.AMOUNT_CURRENCY)),5)
            ELSE 0.00
        END AS CURRENCY_RATE,
        CASE
            WHEN ROUND(SUM (AML.AMOUNT_CURRENCY),4) > 0
            THEN ROUND(SUM (AML.AMOUNT_CURRENCY),4)
            ELSE 0.00
        END AS DEBIT_CURRENCY,
        CASE
            WHEN ROUND(SUM (AML.AMOUNT_CURRENCY),4) < 0
            THEN -1 * ROUND(SUM (AML.AMOUNT_CURRENCY),4)
            ELSE 0.00
        END AS CREDIT_CURRENCY,
        ROUND(SUM (AML.AMOUNT_CURRENCY),4) AS AMOUNT_CURRENCY,
        RC.SYMBOL AS SYMBOL
        FROM ACCOUNT_MOVE_LINE AML
        LEFT JOIN ACCOUNT_JOURNAL AJ ON AJ.ID = AML.JOURNAL_ID
        LEFT JOIN ACCOUNT_MOVE INV ON INV.ID = AML.MOVE_ID
        LEFT JOIN RES_CURRENCY RC ON RC.ID = AML.CURRENCY_ID
        WHERE AML.FULL_RECONCILE_ID = %(id)s
        GROUP BY AML.DATE,
        AJ.NAME,
        INV.NUMBER,
        INV.SUPPLIER_INVOICE_NUMBER,
        RC.SYMBOL
        ORDER BY AML.DATE,RC.SYMBOL"""

        self.env.cr.execute(query, {"id": self.id})
        res = self.env.cr.dictfetchall()

        return res
