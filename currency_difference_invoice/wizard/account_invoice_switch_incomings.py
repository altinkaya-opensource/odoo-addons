from odoo import models, api, _
from odoo.exceptions import ValidationError


class AccountInvoiceSwitchIncomings(models.TransientModel):
    _name = "account.invoice.switch.incomings"
    _description = "Account Invoice Switch Incomings"

    
    def switch_invoices(self):
        context = dict(self._context)
        active_ids = context.get('active_ids', [])
        invoices = self.env['account.move'].browse(active_ids)
        old_invoice = invoices.filtered(lambda i: i.state == 'draft')
        einvoice = invoices.filtered(lambda i: i.einvoice_uuid)

        if any(x != 'out_refund' for x in invoices.mapped('move_type')):
            raise ValidationError(_('You can only switch incoming invoices.'))

        if invoices.mapped('journal_id.code') != ['KFARK']:
            raise ValidationError(_('You can only switch currency difference invoices.'))

        if einvoice.state == 'draft':
            raise ValidationError(_('You can not switch draft e-invoices. Please validate them first.'))

        if old_invoice.amount_total != einvoice.amount_total:
            raise ValidationError(_('You can only switch invoices with same amount.'))

        if len(invoices.mapped('partner_id')) != 1:
            raise ValidationError(_('You can only switch invoices with same partner.'))

        currency_diff_aml = old_invoice.mapped(
            'full_reconcile_ids.reconciled_line_ids').filtered(lambda a: a.journal_id.code == 'KRFRK')

        new_currency_diff_aml = einvoice.line_ids.filtered(
            lambda a: '320' in a.account_id.code)

        aml_to_reconcile = old_invoice.mapped(
            'full_reconcile_ids.reconciled_line_ids') - currency_diff_aml

        old_invoice.mapped('full_reconcile_ids').unlink()
        aml_to_reconcile._reconcile(diff_aml=new_currency_diff_aml)

        old_invoice.unlink()

        return {'type': 'ir.actions.act_window_close'}
