# Copyright 2025 Ismail Çağan Yılmaz (https://github.com/milleniumkid)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import Command, _, api, fields, models
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

    currency_difference_line_ids = fields.Many2many(
        "account.move.line",
        string="Currency Difference Lines",
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

    @api.depends("move_type")
    def _compute_invoice_default_sale_person(self):
        """
        Overriden to use partner's default sale person since we're
        creating invoices from warehouse operations.
        """
        for move in self:
            if move.is_sale_document(include_receipts=True):
                move.invoice_user_id = (
                    move.partner_id.commercial_partner_id.user_id or self.env.user
                )
            else:
                move.invoice_user_id = False

    @api.model
    def _compute_full_reconcile_ids(self):
        for invoice in self:
            if invoice.state == "draft" and invoice.currency_difference_line_ids:
                invoice.full_reconcile_ids = (
                    invoice.currency_difference_line_ids.mapped("full_reconcile_id")
                )
            elif invoice.state == "posted" and invoice.invoice_line_ids:
                invoice.full_reconcile_ids = invoice.line_ids.mapped(
                    "full_reconcile_id"
                )
            else:
                invoice.full_reconcile_ids = False

    @api.depends("full_reconcile_ids")
    def _compute_other_inv_in_reconciles(self):
        invoice_amls = self.full_reconcile_ids.mapped("reconciled_line_ids").filtered(
            lambda x: x.move_id and x.move_id.is_invoice()
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

        if not res:  # This means post was successful
            # Currency difference invoice
            for invoice in self.filtered(lambda x: x.currency_difference_line_ids):
                reconciled_lines = invoice.mapped(
                    "currency_difference_line_ids.full_reconcile_id.reconciled_line_ids"
                )
                old_difference_lines = reconciled_lines.filtered(
                    lambda aml: aml.journal_code == "KRFRK"
                )

                aml_to_reconcile = reconciled_lines - old_difference_lines

                new_currency_diff_line = invoice.line_ids.filtered(
                    lambda ml: ml.account_id
                    in (
                        self.partner_id.property_account_payable_id,
                        self.partner_id.property_account_receivable_id,
                    )
                )

                full_to_unlink = reconciled_lines.mapped("full_reconcile_id")
                partials = full_to_unlink.mapped("partial_reconcile_ids")
                full_to_unlink.unlink()

                new_currency_diff_line.amount_residual = 0.0
                new_currency_diff_line.amount_residual_currency = 0.0
                new_currency_diff_line.reconciled = True

                # Create new full with our new line
                self.env["account.full.reconcile"].with_context(
                    skip_invoice_sync=True,
                    skip_invoice_line_sync=True,
                    skip_account_move_synchronization=True,
                    check_move_validity=False,
                ).create(
                    {
                        "partial_reconcile_ids": [Command.set(partials.ids)],
                        "reconciled_line_ids": [
                            Command.set((aml_to_reconcile + new_currency_diff_line).ids)
                        ],
                    }
                )

                moves_to_cancel = old_difference_lines.mapped("move_id")
                for move in moves_to_cancel:
                    move.button_cancel()

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
            if (
                invoice.currency_difference_line_ids
                and invoice.journal_id.code == "KFARK"
            ):
                for line in invoice.currency_difference_line_ids:
                    line.write({"difference_checked": False})

    def unlink(self):
        """
        When unlinking a currency difference invoice, set the related move lines
        difference_checked field to False
        """
        for invoice in self:
            if (
                invoice.currency_difference_line_ids
                and invoice.journal_id.code == "KFARK"
            ):
                for line in invoice.currency_difference_line_ids:
                    line.write({"difference_checked": False})
        return super().unlink()

    def _calculate_hs_code_distribution(self):
        self.ensure_one()
        uom_kg = self.env.ref("uom.product_uom_kgm")
        package_ids = self.picking_ids.mapped("package_ids").filtered(
            lambda p: not p.is_pallet
        )
        hs_code_distribution = {}

        total_calculated_weight = sum(package_ids.mapped("weight")) or 1.0
        total_gross_weight = sum(package_ids.mapped("shipping_weight")) or 1.0

        hs_codes = package_ids.mapped("quant_ids.product_id.categ_id.hs_code_id")
        index = 1

        for hs_code in hs_codes:
            hs_code_quants = package_ids.quant_ids.filtered(
                lambda q: q.product_id.categ_id.hs_code_id == hs_code
            )
            quant_totals = 0.0
            for quant in hs_code_quants:
                quant_totals += quant.product_id.weight_uom_id._compute_quantity(
                    qty=quant.quantity * quant.product_id.product_weight,
                    to_unit=uom_kg,
                    round=False,
                )

            percentage = round(
                (quant_totals / total_calculated_weight * 100)
                if total_calculated_weight
                else 0.0
            )

            gross_distribution = (
                total_gross_weight * (percentage / 100.0) if total_gross_weight else 0.0
            )

            hs_code_distribution[hs_code] = {
                "percentage": percentage,
                "gross_distribution": gross_distribution,
                "index": index,
            }
            index += 1
        return hs_code_distribution
