from odoo import models, api, fields, _
from odoo.exceptions import UserError


class CreateCurrencyDifferenceInvoices(models.TransientModel):
    _name = 'create.currency.difference.invoices'

    invoice_date = fields.Date(string='Invoice Date', required=True, default=fields.Date.context_today)
    payment_term_id = fields.Many2one('account.payment.term', string='Payment Term', required=True)
    billing_point_id = fields.Many2one('account.billing.point', string='Billing Point', required=True)

    @api.multi
    def create_invoices(self):
        context = dict(self._context or {})
        active_ids = context.get('active_ids', []) or []
        partners = self.env['res.partner'].browse(active_ids)
        invoices = self.env['account.invoice']
        for record in self.web_progress_iter(partners, msg="Müşterilerin kur farkı faturaları oluşturuluyor..."):
            inv_id = record.calc_difference_invoice(self.invoice_date, self.payment_term_id, self.billing_point_id)
            if inv_id:
                invoices |= inv_id

        if not invoices:
            raise UserError(_('No invoice created!'))
        action = self.env.ref("account.action_invoice_tree1")
        action_dict = action.read()[0]

        if len(invoices) > 1:
            action_dict['domain'] = [('id', 'in', invoices.ids)]
        elif len(invoices) == 1:
            if invoices.type in ["out_invoice", "out_refund"]:
                form_view = [(self.env.ref('account.invoice_form').id, 'form')]
            else:
                form_view = [(self.env.ref('account.invoice_supplier_form').id, 'form')]
            if 'views' in action_dict:
                action_dict['views'] = form_view + [(state,  view) for state, view in action['views'] if view != 'form']
            else:
                action_dict['views'] = form_view
            action_dict['res_id'] = invoices.id

        return action_dict

