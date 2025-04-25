from odoo import _, api, models


class AccountPartialReconcile(models.Model):
    _inherit = "account.partial.reconcile"

    @api.model
    def create_exchange_rate_entry(self, aml_to_fix, move):
        """
        Automatically create a journal items to book the exchange rate
        differences that can occur in multi-currencies environment. That
        new journal item will be made into the given `move` in the company
        `currency_exchange_journal_id`, and one of its journal items is
        matched with the other lines to balance the full reconciliation.

        :param aml_to_fix: recordset of account.move.line (possible several
            but sharing the same currency)
        :param move: account.move
        :return: tuple.
            [0]: account.move.line created to balance the `aml_to_fix`
            [1]: recordset of account.partial.reconcile created between the
                tuple first element and the `aml_to_fix`
        """
        aml_model = self.env["account.move.line"]
        total = sum(aml.amount_residual for aml in aml_to_fix)
        created_lines = self.env["account.move.line"]
        currency_id = aml_to_fix[
            0
        ].partner_id.property_account_receivable_id.currency_id

        # create the line that will compensate all the aml_to_fix
        line_to_rec = aml_model.with_context(check_move_validity=False).create(
            {
                "name": _("Currency exchange rate difference"),
                "debit": total < 0 and -total or 0.0,
                "credit": total > 0 and total or 0.0,
                "account_id": aml_to_fix[0].account_id.id,
                "currency_id": currency_id.id,
                "amount_currency": 0.0,
                "move_id": move.id,
                "partner_id": aml_to_fix[0].partner_id.id,
            }
        )
        # create the counterpart on exchange gain/loss account
        if aml_to_fix[0].partner_id.country_id.id == 224:  # Turkey
            exchange_journal = move.company_id.currency_exchange_journal_id
        else:
            exchange_journal = move.env["account.journal"].search(
                [("code", "=", "KRDGR")], limit=1
            )
            move.journal_id = exchange_journal
        aml_model.with_context(check_move_validity=False).create(
            {
                "name": _("Currency exchange rate difference"),
                "debit": total > 0 and total or 0.0,
                "credit": total < 0 and -total or 0.0,
                "account_id": total > 0
                and exchange_journal.default_debit_account_id.id
                or exchange_journal.default_credit_account_id.id,
                "move_id": move.id,
                "currency_id": currency_id.id,
                "amount_currency": 0.0,
                "partner_id": aml_to_fix[0].partner_id.id,
            }
        )

        # # reconcile all aml_to_fix
        # partial_rec |= self.create(
        #     self._prepare_exchange_diff_partial_reconcile(
        #         aml=aml,
        #         line_to_reconcile=line_to_rec,
        #         currency=aml.currency_id or False)
        # )
        created_lines |= line_to_rec
        return created_lines


class AccountFullReconcile(models.Model):
    _inherit = "account.full.reconcile"

    def get_report_data(self):
        """Returns report dictionary for currency difference report for reconcilation"""

        query = """SELECT AML.DATE AS DATE,
    	CASE
    					WHEN INV.SUPPLIER_INVOICE_NUMBER IS NOT NULL
         THEN AJ.NAME || ' ' || INV.SUPPLIER_INVOICE_NUMBER
    					WHEN INV.NUMBER IS NOT NULL THEN AJ.NAME || ' ' || INV.NUMBER
    					ELSE AJ.NAME
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
    LEFT JOIN ACCOUNT_INVOICE INV ON INV.ID = AML.INVOICE_ID
    LEFT JOIN RES_CURRENCY RC ON RC.ID = AML.CURRENCY_ID
    WHERE AML.FULL_RECONCILE_ID = %s
    GROUP BY AML.DATE,
        AJ.NAME,
    	INV.NUMBER,
    	INV.SUPPLIER_INVOICE_NUMBER,
    	RC.SYMBOL
        ORDER BY AML.DATE,RC.SYMBOL"""

        self.env.cr.execute(query, (self.id))
        res = self.env.cr.dictfetchall()

        return res

    def unlink(self):
        """
        When removing a full reconciliation, we choose
        to remove partial reconciliations also
        """
        partial_rec_to_unlink = self.env["account.partial.reconcile"]

        for rec in self:
            partial_rec_to_unlink |= rec.partial_reconcile_ids

        res = super().unlink()
        partial_rec_to_unlink.unlink()
        return res
