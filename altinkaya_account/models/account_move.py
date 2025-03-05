# Copyright 2025 Ismail Çağan Yılmaz (https://github.com/milleniumkid)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import api, fields, models, _


class AccountMove(models.Model):
    _inherit = "account.move"

    total_balance = fields.Float(compute="_compute_partner_balance")

    x_comment_export = fields.Text("ihracat fatura notu")
    z_tevkifatli_mi = fields.Boolean(
        "Tevkifatlı",
        help="Eger fatura tevkifatli fatura ise bu alan secilmeli Sadece zirve programi transferinde kullanilmaktadir.",
    )
    carrier_id = fields.Many2one("delivery.carrier", "Carrier")
    x_serino = fields.Char("Fatura No", size=64)
    x_teslimat = fields.Char("Teslimat Kisaltmasi", size=64)
    address_contact_id = fields.Many2one("res.partner", "Shipping Address")
    receiver = fields.Char(string="Reciever")
    supplier_invoice_number = fields.Char(
        string="Supplier Invoice Number",
        help="The reference of this invoice as provided by the supplier.",
        readonly=True,
        states={"draft": [("readonly", False)]},
    )

    waiting_picking_ids = fields.Many2many(
        "stock.picking",
        string="Waiting Pickings",
        compute="_compute_waiting_picking_ids",
    )

    def _compute_partner_balance(self):
        for move in self:
            partner = move.partner_id
            if partner.commercial_partner_id != partner:
                comm_partner = partner.commercial_partner_id
                balance = comm_partner.credit - comm_partner.debit
            else:
                balance = partner.credit - partner.debit
            move.total_balance = balance

    def _compute_waiting_picking_ids(self):
        stocks = self.env["stock.picking"].search(
            [
                ("partner_id", "=", self.partner_id.id),
                ("picking_type_id.code", "=", "incoming"),
                ("invoice_state", "=", "2binvoiced"),
            ]
        )

        return stocks

    def action_post(self):
        res = super().action_post()
        user = self.env.user
        for move in self:
            for picking in move.picking_ids:
                if picking.carrier_id.id != move.carrier_id.id:
                    picking.message_post(
                        body=_(
                            "Carrier changed from %(frm)s to %(to)s through "
                            "invoice by %(user)s",
                            frm=picking.carrier_id.name,
                            to=move.carrier_id.name,
                            user=user.name,
                        )
                    )
                    picking.write({"carrier_id": move.carrier_id.id})

            if move.payment_term_id and move.payment_term_id.convert_invoice_to_try:
                move.currency_id = self.env.ref("base.TRY")
                move._onchange_currency()
                move._compute_currency_change_rate()
                move.action_account_change_currency()

            move._onchange_quick_edit_line_ids()  # Recompute taxes
            if (
                move.move_type == "in_invoice"
                and fields.first(move.invoice_line_ids).account_id
            ):
                move.partner_id.write(
                    {
                        "purchase_default_account_id": fields.first(
                            move.invoice_line_ids
                        ).account_id.id
                    }
                )

        return res
