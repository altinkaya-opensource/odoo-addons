# -*- coding: utf-8 -*-

from odoo import models, fields, api, _


class AccountInvoice(models.Model):
    _inherit = 'account.move'

    @api.depends('invoice_line_ids', 'state', 'line_ids')
    def _compute_full_reconcile_ids(self):
        for invoice in self:
            if invoice.state == 'draft' and invoice.invoice_line_ids:
                invoice.full_reconcile_ids = invoice.invoice_line_ids.mapped(
                    'difference_base_aml_id').mapped('full_reconcile_id')
            elif invoice.state in ['posted'] and invoice.invoice_line_ids:
                invoice.full_reconcile_ids = invoice.line_ids.mapped('full_reconcile_id')
            else:
                invoice.full_reconcile_ids = False

    @api.depends('full_reconcile_ids')
    def _compute_other_inv_in_reconciles(self):
        invoice_amls = self.full_reconcile_ids.mapped('reconciled_line_ids').filtered(lambda x: x.move_id)
        self.other_inv_in_reconciles = invoice_amls.mapped('move_id')

    full_reconcile_ids = fields.Many2many('account.full.reconcile',
                                          string='Full Reconciles',
                                          compute='_compute_full_reconcile_ids',
                                          help="Full reconciles linked to this invoice")

    other_inv_in_reconciles = fields.Many2many('account.move', string='Other invoices in reconciles',
                                               compute='_compute_other_inv_in_reconciles')

    def action_register_payment(self):
        if not self:
            return True
        return super(AccountInvoice, self).action_register_payment()


    def action_post(self):
        """
        For currency difference Invoices Override method to unreconcile previous account move lines and
        reconcie new account move lines
        """
        res = super(AccountInvoice, self).action_post()

        if not self:
            return res

        for invoice in self:
            aml_to_unreconcile = self.env['account.move.line']
            aml_to_reconcile = self.env['account.move.line']
            for inv_line in invoice.invoice_line_ids.filtered(lambda x: x.difference_base_aml_id):
                aml_to_unreconcile |= inv_line.difference_base_aml_id.full_reconcile_id.reconciled_line_ids
                aml_to_reconcile |= inv_line.difference_base_aml_id.full_reconcile_id.reconciled_line_ids.filtered(
                    lambda r: r.id != inv_line.difference_base_aml_id.id)

            if aml_to_unreconcile:
                aml_to_unreconcile.remove_move_reconcile()

            if aml_to_reconcile:
                diff_aml = invoice.line_ids.filtered(lambda r: not r.reconciled and
                                                                       r.account_id.account_type in
                                                                       ('liability_payable', 'asset_receivable'))
                (aml_to_reconcile | diff_aml)._reconcile()
        return res


    def button_cancel(self):
        res = super(AccountInvoice, self).button_cancel()

        if not self:
            return res

        for invoice in self:
            if invoice.invoice_line_ids and invoice.journal_id.code == 'KFARK':
                for line in invoice.invoice_line_ids.filtered(lambda x: x.difference_base_aml_id):
                    line.difference_base_aml_id.write({'difference_checked': False})


    def unlink(self):
        for invoice in self:
            if invoice.invoice_line_ids and invoice.journal_id.code == 'KFARK':
                for line in invoice.invoice_line_ids.filtered(lambda x: x.difference_base_aml_id):
                    line.difference_base_aml_id.write({'difference_checked': False})
        return super(AccountInvoice, self).unlink()
