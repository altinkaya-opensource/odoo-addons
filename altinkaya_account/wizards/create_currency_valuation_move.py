from odoo import fields, models


class CreateCurrencyValuationMove(models.TransientModel):
    _name = "create.currency.valuation.move"
    _description = "Transient Model For Currency Valuation Move"

    move_date = fields.Date(required=True, default=fields.Date.context_today)
    rate_field = fields.Selection(
        selection=lambda self: self.env["res.currency.rate"]._get_rate_fields(),
        string="Currency Rate Field",
        required=True,
        default="tcmb_forex_buying",
    )

    def create_move(self):
        context = dict(self._context or {})
        active_ids = context.get("active_ids", []) or []
        partners = (
            self.env["res.partner"].browse(active_ids).mapped("commercial_partner_id")
        )
        created_move = partners.calc_currency_valuation(
            self.move_date, rate_field=self.rate_field
        )

        action_dict = self.env.ref("account.action_move_journal_line").read()[0]
        form_view = [(self.env.ref("account.view_move_form").id, "form")]
        action_dict["views"] = form_view + [
            (view_id, view_type)
            for view_id, view_type in action_dict.get("views", [])
            if view_type != "form"
        ]
        action_dict["res_id"] = created_move.id

        return action_dict
