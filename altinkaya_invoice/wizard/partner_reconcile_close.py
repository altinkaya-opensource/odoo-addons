# -*- encoding: utf-8 -*-
#
# Created on Dec 4, 2018
#
# @author: dogan
#

from odoo import models, fields, api, _

import logging

_logger = logging.getLogger(__name__)


class PartnerReconcileClose(models.TransientModel):
    """
    Wizard for reconciliation of account move lines and creating closing/opening moves
    """
    _name = 'partner.reconcile.close'

    country_id = fields.Many2one('res.country', string='Partner Country')
    customer = fields.Boolean('Customer')
    supplier = fields.Boolean('Supplier')
    partner_id = fields.Many2one('res.partner', string='Partner')
    transfer_journal_id = fields.Many2one('account.journal', string='Transfer Journal', required=True)
    transfer_account_id = fields.Many2one('account.account', string='Transfer Account', required=True)
    transfer_description = fields.Char('Transfer description', required=True)
    start_date = fields.Date('Start Date', required=True)
    end_date = fields.Date('End Date', required=True)
    opening_move_date = fields.Date('Opening Move Date', required=True)
    closing_move_date = fields.Date('Closing Move Date', required=True)



    @api.onchange('country_id', 'customer', 'supplier')
    def onchange_country_id(self):
        domain = []
        if self.country_id:
            domain.append(('country_id', '=', self.country_id.id))

        if self.customer and not self.supplier:
            domain.append(('customer', '=', True))

        if not self.customer and self.supplier:
            domain.append(('supplier', '=', True))

        if self.customer and self.supplier:
            domain.extend(['|', ('customer', '=', True), ('supplier', '=', True)])

        return {'domain': {'partner_id': domain}}

    @api.multi
    def action_done(self):

        self.ensure_one()
        domain = [('date', '>=', self.start_date), ('date', '<=', self.end_date)]
        partner_ids = self.env['res.partner']
        move_obj = self.env['account.move']
        move_line_obj = self.env['account.move.line'].with_context({'comment': self.transfer_description})
        if self.partner_id:
            partner_ids |= self.partner_id
        else:
            partner_domain = [('parent_id', '=', False)]

            if self.country_id:
                partner_domain.append(('country_id', '=', self.country_id.id))

            if self.customer and not self.supplier:
                partner_domain.append(('customer', '=', True))

            if not self.customer and self.supplier:
                partner_domain.append(('supplier', '=', True))

            if self.customer and self.supplier:
                partner_domain.extend(['|', ('customer', '=', True), ('supplier', '=', True)])

            partner_ids = self.env['res.partner'].search(partner_domain)

        closing_move_id = move_obj.create({
            'journal_id': self.transfer_journal_id.id,
            'date': self.closing_move_date,
            'state': 'draft'
        })

        opening_move_id = move_obj.create({
            'journal_id': self.transfer_journal_id.id,
            'date': self.opening_move_date,
            'state': 'draft'
        })

        for partner in partner_ids:
            if partner.devir_yapildi:
                continue
            try:

                for account in [partner.property_account_receivable, partner.property_account_payable]:
                    
                    lines = move_line_obj.search(
                        domain + [('partner_id', '=', partner.id), ('account_id', '=', account.id)])
                    if len(lines) == 0:
                        continue
                    
                    balance = sum([ml.debit - ml.credit for ml in lines])
                    date_due = max(lines.mapped('date_maturity'))
                    
                    if balance > 0:
                        debit = balance
                        credit = 0.0
                        self_credit = balance
                        self_debit = 0.0
                    elif balance < 0:
                        debit = 0.0
                        credit = -balance
                        self_credit = 0.0
                        self_debit = -balance
                    else:
                        continue

                    lines |= closing_move_id.line_id.create({
                        'move_id': closing_move_id.id,
                        'name': _('Closing'),
                        'debit': self_debit,
                        'credit': self_credit,
                        'account_id': account.id,
                        'date': self.closing_move_date,
                        'date_maturity':date_due,
                        'partner_id': partner.id,
                        'currency_id': (account.currency_id.id or False)
                    })

                    closing_move_id.line_id.create({
                        'move_id': closing_move_id.id,
                        'name': _('Closing'),
                        'debit': debit,
                        'credit': credit,
                        'account_id': self.transfer_account_id.id,
                        'date': self.closing_move_date,
                        'date_maturity':date_due,
                        'partner_id': partner.id,
                        'currency_id': (account.currency_id.id or False)
                    })

                    opening_move_id.line_id.create({
                        'move_id': opening_move_id.id,
                        'name': _('Opening'),
                        'debit': debit,
                        'credit': credit,
                        'account_id': account.id,
                        'date': self.opening_move_date,
                        'date_maturity':date_due,
                        'partner_id': partner.id,
                    })
                    opening_move_id.line_id.create({
                        'move_id': opening_move_id.id,
                        'name': _('Opening'),
                        'debit': self_debit,
                        'credit': self_credit,
                        'account_id': self.transfer_account_id.id,
                        'date': self.opening_move_date,
                        'date_maturity':date_due,
                        'partner_id': partner.id,
                    })

                    move_line_obj._remove_move_reconcile(lines.ids)
                    lines.reconcile()

                partner.devir_yapildi = True
                _logger.error('Partner reconcilation done. Partner: %s \n\n' % partner.name)
                self._cr.commit()

            except Exception as  e:
                _logger.exception(
                    'Partner reconciliation wizard error. Partner: %s \n\n %s' % (partner.name, e.message))

        closing_move_id.post()
        opening_move_id.post()

        return {
            'name': _('Account Moves'),
            'view_type': 'form',
            'view_mode': 'tree',
            'res_model': 'account.move',
            'view_id': False,
            'type': 'ir.actions.act_window',
            'domain': [('id', 'in', [opening_move_id.id, closing_move_id.id])],
            'context': self._context
        }
