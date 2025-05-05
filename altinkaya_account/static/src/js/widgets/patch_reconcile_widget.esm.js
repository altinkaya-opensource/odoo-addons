/** @odoo-module **/
/* Copyright 2025 Ahmet Yiğit Budak - ALTINKAYA
 * License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl). */
import { AccountReconcileDataWidget } from "@account_reconcile_oca/js/widgets/reconcile_data_widget.esm";
import fieldUtils from "web.field_utils";
import { patch } from "@web/core/utils/patch";
import session from "web.session";

patch(AccountReconcileDataWidget.prototype, "altinkaya_account.AccountReconcileDataWidget", {
    getTotals() {
        const data = this.getReconcileLines();
        if (data.length === 0) {
            return false;
        }
        const totals = {
            debit: 0,
            credit: 0,
            amount_currency: 0,
        };

        for (const line of data) {
            totals.debit += line.debit;
            totals.credit += line.credit;
            totals.amount_currency += line.currency_amount;
        }

        const last_line_currency = data[data.length - 1].line_currency_id;
        const last_line_currency_id = data[data.length - 1].currency_id;

        // Format the totals
        totals.debit_format = fieldUtils.format.monetary(totals.debit, undefined, {
            currency: session.get_currency(last_line_currency_id),
        });
        totals.credit_format = fieldUtils.format.monetary(totals.credit, undefined, {
            currency: session.get_currency(last_line_currency_id),
        });
        totals.amount_currency_format = fieldUtils.format.monetary(totals.amount_currency, undefined, {
            currency: session.get_currency(last_line_currency),
        });

        return totals;
    },

});
