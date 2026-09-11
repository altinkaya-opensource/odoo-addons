from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError


class CreateCurrencyDifferenceInvoice(models.TransientModel):
    _name = "create.currency.difference.invoice"
    _description = "Transient Model For Currency Difference Invoice"

    invoice_date = fields.Date(required=True, default=fields.Date.context_today)
    payment_term_id = fields.Many2one("account.payment.term", required=True)
    billing_point_id = fields.Many2one("account.billing.point", required=True)

    def _get_created_invoices_action(self, invoices):
        """Return the standard customer invoice action for created invoices."""
        self.ensure_one()
        action = self.env.ref("account.action_move_out_invoice_type").read()[0]
        if len(invoices) > 1:
            action["domain"] = [("id", "in", invoices.ids)]
        else:
            form_view = (self.env.ref("account.view_move_form").id, "form")
            action["views"] = [form_view] + [
                (view_id, view_type)
                for view_id, view_type in action.get("views", [])
                if view_type != "form"
            ]
            action["res_id"] = invoices.id
        return action

    def create_invoices(self):
        context = dict(self._context or {})
        active_ids = context.get("active_ids", []) or []
        partners = (
            self.env["res.partner"].browse(active_ids).mapped("commercial_partner_id")
        )
        invoices = self.env["account.move"]
        for record in partners:
            inv_id = record.calc_difference_invoice(
                self.invoice_date, self.payment_term_id, self.billing_point_id
            )
            if inv_id:
                invoices |= inv_id

        if not invoices:
            raise UserError(_("No invoice created!"))
        return self._get_created_invoices_action(invoices)


class CreateSelectedCurrencyDifferenceInvoice(models.TransientModel):
    _name = "create.selected.currency.difference.invoice"
    _inherit = "create.currency.difference.invoice"
    _description = "Create Currency Difference Invoice From Selected Entries"

    partner_id = fields.Many2one("res.partner", required=True, readonly=True)
    company_id = fields.Many2one(
        "res.company",
        required=True,
        readonly=True,
        default=lambda self: self.env.company,
    )
    company_currency_id = fields.Many2one(
        related="company_id.currency_id",
        readonly=True,
    )
    invoice_ids = fields.Many2many(
        "account.move",
        "selected_currency_difference_invoice_move_rel",
        "wizard_id",
        "move_id",
        string="Invoices",
        check_company=True,
    )
    payment_line_ids = fields.Many2many(
        "account.move.line",
        "selected_currency_difference_invoice_line_rel",
        "wizard_id",
        "line_id",
        string="Payments",
        check_company=True,
    )

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        if self.env.context.get("active_model") != "res.partner":
            return values
        partner = (
            self.env["res.partner"].browse(self.env.context.get("active_id")).exists()
        )
        if not partner:
            return values
        partner = partner.commercial_partner_id
        values["partner_id"] = partner.id
        if partner.property_payment_term_id:
            values["payment_term_id"] = partner.property_payment_term_id.id
        values.update(
            self._get_candidate_values(
                partner,
                fields.Date.to_date(values.get("invoice_date"))
                or fields.Date.context_today(self),
            )
        )
        return values

    @api.model
    def _get_candidate_values(self, partner, date):
        """Eligible invoices and payments, ready to be tweaked by the user."""
        invoices, payment_lines = partner._get_currency_difference_candidates(date)
        return {
            "invoice_ids": [Command.set(invoices.ids)],
            "payment_line_ids": [Command.set(payment_lines.ids)],
        }

    @api.onchange("invoice_date")
    def _onchange_invoice_date(self):
        if self.partner_id and self.invoice_date:
            self.update(self._get_candidate_values(self.partner_id, self.invoice_date))

    def action_create_invoice(self):
        self.ensure_one()
        invoices = self.partner_id.calc_selected_difference_invoice(
            self.invoice_date,
            self.payment_term_id,
            self.billing_point_id,
            self.invoice_ids,
            self.payment_line_ids,
        )
        if not invoices:
            raise UserError(_("No invoice created!"))
        return self._get_created_invoices_action(invoices)
