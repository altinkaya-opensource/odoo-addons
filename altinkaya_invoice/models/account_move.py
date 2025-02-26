# -*- encoding: utf-8 -*-
'''
Created on Jan 16, 2019

@author: Codequarters
'''
from odoo import models,fields,api
from werkzeug.urls import url_encode
import hashlib


class AccountMove(models.Model):
    _inherit = 'account.move'

    #altinkaya61
    x_comment_export = fields.Text('ihracaat fatura notu')
    z_tevkifatli_mi = fields.Boolean(';TEVKiFATLI', help="Eger fatura tevkifatli fatura ise bu alan secilmeli Sadece zirve programi transferinde kullanilmaktadir.")

    carrier_id = fields.Many2one('delivery.carrier', 'Carrier')

    x_serino = fields.Char('Fatura No',size=64)
    x_teslimat = fields.Char('Teslimat Kisaltmasi',size=64)
    address_contact_id = fields.Many2one('res.partner','Shipping Address')
    receiver = fields.Char(string="Reciever")

    #TODO this is not required we can use invoice.number field for supplier invoices
    supplier_invoice_number = fields.Char(string='Supplier Invoice Number',
        help="The reference of this invoice as provided by the supplier.",
        readonly=True, states={'draft': [('readonly', False)]})

    waiting_picking_ids = fields.One2many('stock.picking', string="Waiting Pickings",
                                          compute="_compute_waiting_picking_ids")

    def _compute_waiting_picking_ids(self):

        stocks = self.env['stock.picking'].search([('partner_id', '=', self.partner_id.id),
                                                   ('picking_type_id.code', '=', 'incoming'),
                                                   ('invoice_state', '=', '2binvoiced')])

        return stocks


    #TDE Fix Onur
    #invoice have picking_ids but not yet

    def invoice_validate(self):
        res = super(AccountInvoice, self).invoice_validate()
        user = self.env['res.users'].browse(self.env.user.id)
        for invoice in self:
            for picking in invoice.picking_ids:
                if picking.carrier_id.id != invoice.carrier_id.id:
                    picking.message_post(body='Carrier changed from %s to %s through invoice by %s' % (picking.carrier_id.name,invoice.carrier_id.name, user.name))
                    picking.write({'carrier_id':invoice.carrier_id.id})

        return res

    def action_invoice_open(self):
        """
        Inherited to add controls over invoice validation.
        :return:
        """
        for invoice in self:

            # Check if payment term forces to use TRY currency
            if invoice.payment_term_id and invoice.payment_term_id.convert_invoice_to_try:
                invoice.currency_id = self.env.ref('base.TRY')
                invoice._onchange_currency()
                invoice._onchange_currency_change_rate()
                invoice.action_account_change_currency()

            # write suppliers selected expense account to partner record and use it for next invoice
            invoice._onchange_invoice_line_ids()  # Recompute taxes
            if invoice.type == 'in_invoice' and fields.first(invoice.invoice_line_ids).account_id:
                invoice.partner_id.write({"purchase_default_account_id": fields.first(invoice.invoice_line_ids).account_id.id})
        return super(AccountInvoice, self).action_invoice_open()
