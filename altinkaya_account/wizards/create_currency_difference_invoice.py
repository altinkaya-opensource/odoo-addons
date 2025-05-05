from odoo import _, fields, models
from odoo.exceptions import UserError


class CreateCurrencyDifferenceInvoice(models.TransientModel):
    _name = "create.currency.difference.invoice"
    _description = "Transient Model For Currency Difference Invoice"

    invoice_date = fields.Date(required=True, default=fields.Date.context_today)
    payment_term_id = fields.Many2one(
        "account.payment.term", string="Payment Term", required=True
    )
    billing_point_id = fields.Many2one(
        "account.billing.point", string="Billing Point", required=True
    )

    def create_invoices(self):
        context = dict(self._context or {})
        active_ids = context.get("active_ids", []) or []
        partners = self.env["res.partner"].browse(active_ids)
        invoices = self.env["account.move"]
        for record in partners:
            inv_id = record.calc_difference_invoice(
                self.invoice_date, self.payment_term_id, self.billing_point_id
            )
            if inv_id:
                invoices |= inv_id

        if not invoices:
            raise UserError(_("No invoice created!"))
        # action = self.env.ref("account.view_out_invoice_tree")
        # action_dict = action.read()[0]

        # if len(invoices) > 1:
        #     action_dict["domain"] = [("id", "in", invoices.ids)]
        # elif len(invoices) == 1:
        #     form_view = [(self.env.ref("account.view_move_form").id, "form")]
        #     if "views" in action_dict:
        #         action_dict["views"] = form_view + [
        #             (state, view) for state, view in action["views"] if view != "form"
        #         ]
        #     else:
        #         action_dict["views"] = form_view
        #     action_dict["res_id"] = invoices.id

        # return action_dict
