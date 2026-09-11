# Copyright 2025 Ismail Çağan Yılmaz (https://github.com/milleniumkid)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import logging

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


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
    carrier_id = fields.Many2one("delivery.carrier")
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

    tax_line_ids = fields.Many2many(
        "account.move.line",
        string="Tax Lines",
        compute="_compute_tax_line_ids",
    )

    currency_difference_line_ids = fields.Many2many(
        "account.move.line",
        string="Currency Difference Lines",
    )
    is_manual_currency_difference = fields.Boolean(copy=False)
    currency_difference_source_invoice_ids = fields.Many2many(
        "account.move",
        "account_move_currency_diff_source_invoice_rel",
        "currency_difference_invoice_id",
        "source_invoice_id",
        string="Source Invoices",
        copy=False,
    )
    currency_difference_source_payment_line_ids = fields.Many2many(
        "account.move.line",
        "account_move_currency_diff_source_payment_rel",
        "currency_difference_invoice_id",
        "source_payment_line_id",
        string="Source Payments",
        copy=False,
    )
    currency_difference_source_move_ids = fields.Many2many(
        "account.move",
        "account_move_currency_diff_source_move_rel",
        "currency_difference_invoice_id",
        "source_move_id",
        string="Source Currency Difference Entries",
        copy=False,
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

    installment_fee_tx_id = fields.Many2one(
        "payment.transaction",
        string="Installment Fee Payment Transaction",
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
            if invoice.state == "posted" and invoice.invoice_line_ids:
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

    def _switch_to_pricelist_currency(self):
        for invoice in self:
            if (
                invoice.is_sale_document()
                and invoice.pricelist_id
                and invoice.pricelist_id.invoice_currency_id
            ):
                invoice.currency_id = invoice.pricelist_id.invoice_currency_id

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

    @api.depends(
        "invoice_payment_term_id",
        "invoice_date",
        "currency_id",
        "amount_total_in_currency_signed",
        "invoice_date_due",
        "partner_id",
        "fiscal_position_id",
        "line_ids.account_id",
    )
    def _compute_needed_terms(self):
        res = super()._compute_needed_terms()
        for move in self:
            if not move.is_invoice(True) or not move.needed_terms:
                continue

            term_account = move.line_ids.filtered(
                lambda line: line.display_type == "payment_term"
            ).account_id[:1]
            if not term_account:
                partner = move.commercial_partner_id.with_company(move.company_id)
                term_account = (
                    partner.property_account_receivable_id
                    if move.is_sale_document(include_receipts=True)
                    else partner.property_account_payable_id
                )
                if term_account and move.fiscal_position_id:
                    term_account = move.fiscal_position_id.map_account(term_account)

            account_currency = term_account.currency_id
            if not account_currency or account_currency == move.currency_id:
                continue

            company_currency = move.company_id.currency_id
            conversion_date = (
                move.invoice_date or move.date or fields.Date.context_today(move)
            )
            needed_terms = {
                key: dict(values) for key, values in move.needed_terms.items()
            }
            for values in needed_terms.values():
                values["amount_currency"] = company_currency._convert(
                    values["balance"],
                    account_currency,
                    move.company_id,
                    conversion_date,
                )
                if values.get("discount_balance"):
                    values["discount_amount_currency"] = company_currency._convert(
                        values["discount_balance"],
                        account_currency,
                        move.company_id,
                        conversion_date,
                    )
            move.needed_terms = needed_terms
        return res

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
            for invoice in self.filtered(
                lambda m: (
                    m.journal_id.code == "KFARK"
                    and m.move_type in ("out_invoice", "out_refund")
                )
            ):
                invoice._reverse_outstanding_krfrk()

        return res

    def _reverse_outstanding_krfrk(self):
        """Replace the automatic exchange-difference (KRFRK) entries billed by
        this KFARK invoice with the invoice itself.

        The outstanding KRFRK moves are reversed with the standard reversal
        mechanism and the reversal's receivable lines are reconciled against
        the invoice's receivable line. Existing reconciliations are never
        touched; when the reversal total differs from the invoice total the
        residual stays open on purpose — it signals ledger data that needs
        repair (currency.reconcile.fix.wizard).
        """
        self.ensure_one()
        recv_line = self.line_ids.filtered(lambda ml: ml.display_type == "payment_term")
        if not recv_line:
            return
        account = recv_line.account_id
        if self.is_manual_currency_difference:
            krfrk_moves = self.currency_difference_source_move_ids.filtered(
                lambda move: (
                    move.journal_id == self.company_id.currency_exchange_journal_id
                    and move.state == "posted"
                    and not move.reversed_entry_id
                    and not move.reversal_move_id
                    and move.line_ids.filtered(
                        lambda line: (
                            line.account_id == account
                            and line.partner_id.commercial_partner_id
                            == self.commercial_partner_id
                        )
                    )
                )
            )
        else:
            krfrk_moves = self.env["account.move"].search(
                [
                    (
                        "journal_id",
                        "=",
                        self.company_id.currency_exchange_journal_id.id,
                    ),
                    ("state", "=", "posted"),
                    ("reversed_entry_id", "=", False),
                    ("reversal_move_id", "=", False),
                    ("line_ids.partner_id", "=", self.commercial_partner_id.id),
                    ("line_ids.account_id", "=", account.id),
                ]
            )
        if not krfrk_moves:
            _logger.info(
                "Kur farkı faturası %s: ters kaydedilecek KRFRK kaydı yok, "
                "fatura satırı açık kalıyor.",
                self.name,
            )
            return
        reversals = krfrk_moves._reverse_moves(
            default_values_list=[
                {
                    "date": self.invoice_date,
                    "ref": _("Currency difference invoice %s", self.name),
                }
            ]
            * len(krfrk_moves)
        )
        reversals.action_post()
        rev_lines = reversals.line_ids.filtered(lambda ml: ml.account_id == account)
        (rev_lines + recv_line).with_context(no_exchange_difference=True).reconcile()
        self.currency_difference_line_ids = [(6, 0, rev_lines.ids)]

    def action_match_einvoice_lines_picking(self):
        """
        Match invoice lines with picking lines
        :return: bool
        """
        for invoice in self:
            if not invoice.picking_ids:
                raise ValidationError(_("No picking linked to this invoice"))
            old_invoice_lines = invoice.invoice_line_ids.filtered(
                lambda line: (
                    not (
                        line.name_xml
                        or line.SellersItemIdentification
                        or line.ManufacturersItemIdentification
                        or line.description
                    )
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

    def _teardown_kfark_reversals(self):
        """Undo the KRFRK reversals created when this KFARK invoice was posted.

        Deleting (not just cancelling) the reversal clears reversal_move_id on
        the original KRFRK move, so it becomes outstanding again and a re-run
        of the wizard reproduces the same invoice. Legacy invoices link the
        original KRFRK lines instead of reversal lines (reversed_entry_id
        unset) — those are left untouched.
        """
        for invoice in self.filtered(
            lambda m: m.journal_id.code == "KFARK" and m.currency_difference_line_ids
        ):
            reversals = invoice.currency_difference_line_ids.move_id.filtered(
                "reversed_entry_id"
            )
            invoice.currency_difference_line_ids = [(5, 0, 0)]
            if reversals:
                (reversals.line_ids | invoice.line_ids).remove_move_reconcile()
                reversals.button_cancel()
                reversals.with_context(force_delete=True).unlink()

    def button_cancel(self):
        res = super().button_cancel()
        self._teardown_kfark_reversals()
        return res

    def button_draft(self):
        res = super().button_draft()
        self._teardown_kfark_reversals()
        return res

    def unlink(self):
        self._teardown_kfark_reversals()
        for invoice in self:
            if invoice.installment_fee_tx_id:
                tx = invoice.installment_fee_tx_id
                tx.installment_fee_invoiced = False
                tx.invoiced_installment_fee = 0.0
                tx.installment_fee_invoice_id = False

        return super().unlink()

    def _calculate_hs_code_distribution(self):
        self.ensure_one()
        uom_kg = self.env.ref("uom.product_uom_kgm")
        package_ids = self.picking_ids.mapped("package_ids").filtered(
            lambda p: not p.is_pallet
        )
        cup_ids = self.picking_ids.mapped("package_ids").filtered(
            lambda p: not p.pallet_id
        )
        hs_code_distribution = {}

        total_calculated_weight = sum(package_ids.mapped("weight")) or 1.0
        total_gross_weight = (
            sum((x.shipping_weight * x.package_multiplier) for x in cup_ids) or 1.0
        )

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
