# Copyright 2025 Ismail Çağan Yılmaz (https://github.com/milleniumkid)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class AccountMove(models.Model):
    _inherit = "account.move"

    total_balance = fields.Float(compute="_compute_partner_balance")

    x_comment_export = fields.Text("ihracat fatura notu")
    z_tevkifatli_mi = fields.Boolean(
        "Tevkifatlı",
        help=(
            "Eger fatura tevkifatli fatura ise bu alan secilmeli "
            "Sadece zirve programi transferinde kullanilmaktadir."
        ),
    )
    carrier_id = fields.Many2one("delivery.carrier", "Carrier")
    x_serino = fields.Char("Fatura No", size=64)
    x_teslimat = fields.Char("Teslimat Kisaltmasi", size=64)
    address_contact_id = fields.Many2one("res.partner", "Shipping Address")
    receiver = fields.Char(string="Reciever")
    supplier_invoice_number = fields.Char(
        help="The reference of this invoice as provided by the supplier.",
        readonly=True,
        states={"draft": [("readonly", False)]},
    )

    waiting_picking_ids = fields.Many2many(
        "stock.picking",
        string="Waiting Pickings",
        compute="_compute_waiting_picking_ids",
    )

    delivery_ref_no = fields.Char(
        string="Delivery Reference No.",
        help="Delivery carrier reference number before"
        " the shipment is sent to the carrier.",
    )

    tax_line_ids = fields.Many2many(
        "account.move.line",
        string="Tax Lines",
        compute="_compute_tax_line_ids",
    )

    full_reconcile_ids = fields.Many2many(
        "account.full.reconcile",
        string="Full Reconciles",
        compute="_compute_full_reconcile_ids",
        help="Full reconciles linked to this invoice",
    )

    other_inv_in_reconciles = fields.Many2many(
        "account.move",
        string="Other invoices in reconciles",
        compute="_compute_other_inv_in_reconciles",
    )

    @api.model
    def _compute_full_reconcile_ids(self):
        for invoice in self:
            if invoice.state == "draft" and invoice.invoice_line_ids:
                invoice.full_reconcile_ids = invoice.invoice_line_ids.mapped(
                    "difference_base_aml_id"
                ).mapped("full_reconcile_id")
            elif (
                invoice.state in ["open", "in_payment", "paid"]
                and invoice.invoice_line_ids
            ):
                invoice.full_reconcile_ids = invoice.move_id.line_ids.mapped(
                    "full_reconcile_id"
                )
            else:
                invoice.full_reconcile_ids = False

    @api.depends("full_reconcile_ids")
    def _compute_other_inv_in_reconciles(self):
        invoice_amls = self.full_reconcile_ids.mapped("reconciled_line_ids").filtered(
            lambda x: x.move_id
        )
        self.other_inv_in_reconciles = invoice_amls.mapped("move_id")

    @api.depends("pricelist_id")
    def _compute_currency_id(self):
        """
        Override to use invoice_currency_id from pricelist when
        computing invoice's currency_id.
        """
        res = super()._compute_currency_id()
        for invoice in self:
            if (
                invoice.is_sale_document()
                and invoice.pricelist_id
                and invoice.pricelist_id.invoice_currency_id
                and invoice.currency_id != invoice.pricelist_id.invoice_currency_id
            ):
                invoice.currency_id = self.pricelist_id.invoice_currency_id
        return res

    def _compute_tax_line_ids(self):
        for move in self:
            move.tax_line_ids = move.line_ids.filtered("tax_repartition_line_id")

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
        for inv in self:
            stocks = self.env["stock.picking"].search(
                [
                    ("partner_id", "=", self.partner_id.id),
                    ("picking_type_id.code", "=", "incoming"),
                    ("invoice_state", "=", "2binvoiced"),
                ]
            )
            inv.waiting_picking_ids = stocks

    def _onchange_invoice_line_ids(self):
        """This method was removed in 16.0 but we've added a simulation of it here"""
        return True
        # for invoice in self:
        #     invoice._onchange_partner_id()
        #     invoice._onchange_date()
        #     invoice._compute_currency_id()
        #     invoice._compute_tax_totals()
        #     invoice._compute_amount()

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

            if (
                move.invoice_payment_term_id
                and move.invoice_payment_term_id.convert_invoice_to_try
            ):
                move.currency_id = self.env.ref("base.TRY")
                move._inverse_currency_id()
                move._compute_currency_change_rate()
                move.action_account_change_currency()

            move._onchange_invoice_line_ids()  # Recompute taxes
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

        # Currency difference invoice
        for invoice in self:
            aml_to_unreconcile = self.env["account.move.line"]
            aml_to_reconcile = self.env["account.move.line"]
            for inv_line in invoice.invoice_line_ids.filtered(
                lambda x: x.difference_base_aml_id
            ):
                aml_to_unreconcile |= inv_line.difference_base_aml_id.full_reconcile_id.reconciled_line_ids  # noqa
                aml_to_reconcile |= inv_line.difference_base_aml_id.full_reconcile_id.reconciled_line_ids.filtered(  # noqa
                    lambda r: r.id != inv_line.difference_base_aml_id.id
                )

            if aml_to_unreconcile:
                aml_to_unreconcile.remove_move_reconcile()

            if aml_to_reconcile:
                diff_aml = invoice.move_id.line_ids.filtered(
                    lambda r: not r.reconciled
                    and r.account_id.internal_type in ("payable", "receivable")
                )
                aml_to_reconcile._reconcile(diff_aml=diff_aml)

        return res

    def action_match_einvoice_lines_picking(self):
        """
        Match invoice lines with picking lines
        :return: bool
        """
        for invoice in self:
            if not invoice.picking_ids:
                raise ValidationError(_("No picking linked to this invoice"))
            old_invoice_lines = invoice.invoice_line_ids.filtered(
                lambda line: not (
                    line.name_xml
                    or line.SellersItemIdentification
                    or line.ManufacturersItemIdentification
                    or line.description
                )
            )
            old_invoice_lines.unlink()
            for picking in invoice.picking_ids:
                moves = picking.mapped("move_lines")
                for move in moves:
                    partner_order_ref = move._get_partner_order_ref()
                    move_picking_ref = move._get_picking_ref()
                    invoice_line = invoice.invoice_line_ids.filtered(
                        lambda l: l.product_id == move.product_id
                    )
                    purchase_line = move.purchase_line_id
                    # Link Invoice Lines with Move and Purchase Line
                    invoice_line.write(
                        {
                            "purchase_id": picking.purchase_id.id,
                            "purchase_line_id": purchase_line.id,
                            "move_line_ids": [(6, 0, move.move_line_ids.ids)],
                            "partner_order_ref": partner_order_ref,
                            "moves_picking_ref": move_picking_ref,
                        }
                    )
                    # Link Move with Invoice Lines
                    move.write(
                        {
                            "invoice_line_ids": [(6, 0, invoice_line.ids)],
                        }
                    )
            invoice._compute_tax_totals()
            invoice._create_missing_supplierinfo()
        return True

    def _must_check_constrains_date_sequence(self):
        # Overriden to disable weird sequence check in Odoo
        # that is not needed for our use case
        # and causes issues with the Turkish e-invoice
        # and supplier invoice numbers
        super()._must_check_constrains_date_sequence()
        return False

    def button_cancel(self):
        res = super().button_cancel()

        if not self:
            return res

        for invoice in self:
            if invoice.invoice_line_ids and invoice.journal_id.code == "KFARK":
                for line in invoice.invoice_line_ids.filtered(
                    lambda x: x.difference_base_aml_id
                ):
                    line.difference_base_aml_id.write({"difference_checked": False})

    def unlink(self):
        """
        When unlinking a currency difference invoice, set the related move lines
        difference_checked field to False
        """
        for invoice in self:
            if invoice.invoice_line_ids and invoice.journal_id.code == "KFARK":
                for line in invoice.invoice_line_ids.filtered(
                    lambda x: x.difference_base_aml_id
                ):
                    line.difference_base_aml_id.write({"difference_checked": False})
        return super().unlink()
