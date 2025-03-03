##############################################################################
#
#    Copyright (C) 2015, Eska Yazılım ve Danışmanlık A.Ş.
#    http://www.eskayazilim.com.tr
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

# Copyright 2024 Ismail Cagan Yilmaz (https://github.com/milleniumkid)
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = "account.move"

    @api.depends("amount_total", "currency_id")
    def _compute_invoice_amount_in_words(self):
        for record in self:
            record.invoice_amount_in_words = ""
            try:
                lang = record.env.context.get(
                    "lang", record.sudo().company_id.partner_id.lang
                )
                record.invoice_amount_in_words = record.currency_id.with_context(
                    lang=lang
                ).amount_to_text(record.amount_total)
            except Exception as e:
                _logger.error(f"Error computing invoice amount in words: {e}")

    invoice_amount_in_words = fields.Char(
        compute="_compute_invoice_amount_in_words", string="Amount in Words"
    )


class SaleOrder(models.Model):
    _inherit = "sale.order"

    @api.depends("amount_total", "currency_id")
    def _compute_sale_order_amount_in_words(self):
        for record in self:
            record.sale_order_amount_in_words = ""
            try:
                lang = (
                    record.env.context.get("lang")
                    or record.partner_id.lang
                    or record.sudo().company_id.partner_id.lang
                )
                record.sale_order_amount_in_words = record.currency_id.with_context(
                    lang=lang
                ).amount_to_text(record.amount_total)
            except Exception as e:
                _logger.error(f"Error computing sale order amount in words: {e}")

    sale_order_amount_in_words = fields.Char(
        compute="_compute_sale_order_amount_in_words", string="Amount to Text"
    )


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    @api.depends("amount_total", "currency_id")
    def _compute_purchase_order_amount_in_words(self):
        for record in self:
            record.purchase_order_amount_in_words = ""
            try:
                lang = record.env.context.get(
                    "lang", record.sudo().company_id.partner_id.lang
                )
                record.purchase_order_amount_in_words = record.currency_id.with_context(
                    lang=lang
                ).amount_to_text(record.amount_total)
            except Exception as e:
                _logger.error(f"Error computing purchase order amount in words: {e}")

    purchase_order_amount_in_words = fields.Char(
        compute="_compute_purchase_order_amount_in_words", string="Amount to Text"
    )


class AccountPayment(models.Model):
    _inherit = "account.payment"

    @api.depends("amount", "currency_id")
    def _compute_account_payment_amount_in_words(self):
        for record in self:
            record.account_payment_amount_in_words = ""
            try:
                lang = record.env.context.get(
                    "lang", record.sudo().company_id.partner_id.lang
                )
                record.account_payment_amount_in_words = (
                    record.currency_id.with_context(lang=lang).amount_to_text(
                        record.amount
                    )
                )
            except Exception as e:
                _logger.error(f"Error computing account payment amount in words: {e}")

    account_payment_amount_in_words = fields.Char(
        compute="_compute_account_payment_amount_in_words", string="Amount to Text"
    )
