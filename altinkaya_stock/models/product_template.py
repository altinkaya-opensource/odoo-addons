from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ProductTemplate(models.Model):
    _inherit = "product.template"

    default_code = fields.Char(copy=False)
    responsible_employee_id = fields.Many2one(
        comodel_name="hr.employee", string="Responsible Employee"
    )
    def action_view_todo_moves(self):
        self.ensure_one()
        action = self.env.ref("altinkaya_stock.stock_move_line_action").read()[0]
        action["domain"] = [("product_id", "=", self.id)]
        return action

    @api.constrains("default_code")
    def _check_default_code_unique(self):
        for template in self:
            if template.default_code:
                if (
                    self.search_count([("default_code", "=", template.default_code)])
                    > 1
                ):
                    raise UserError(_("The default code must be unique."))

    @api.depends("company_id")
    def _compute_currency_id(self):
        """
        Overriden to select the currency between the category's currency
        and the company's currency.
        """
        main_company = self.env["res.company"]._get_main_company()
        for template in self:
            if template.categ_id.currency_id:
                template.currency_id = template.categ_id.currency_id.id
            else:
                template.currency_id = (
                    template.company_id.sudo().currency_id.id
                    or main_company.currency_id.id
                )

    @api.depends_context("company")
    def _compute_cost_currency_id(self):
        """
        Overriden to select the cost currency between the category's
        currency and the company's currency.
        """
        main_company = self.env["res.company"]._get_main_company()
        for template in self:
            if template.categ_id.currency_id:
                template.cost_currency_id = template.categ_id.currency_id.id
            else:
                template.cost_currency_id = (
                    template.company_id.sudo().currency_id.id
                    or main_company.currency_id.id
                )

    def _guess_main_lang(self):
        super()._guess_main_lang()
        turkish = self.env.ref("base.lang_tr")
        if turkish.active:
            return turkish.code
        else:
            return self.env["res.lang"].search([], limit=1).code
