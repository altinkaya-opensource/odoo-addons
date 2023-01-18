# Copyright 2022 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo import models, fields, _, api
from odoo.exceptions import UserError
from odoo.addons.http_routing.models.ir_http import slug


class SaleOrder(models.Model):
    _inherit = "sale.order"

    survey_ids = fields.One2many(
        "survey.user_input",
        "sale_id",
        string="Surveys",
    )
    survey_count = fields.Integer(
        compute="_compute_survey_count",
        string="Survey Count",
    )

    survey_url = fields.Char(
        compute="_compute_survey_url",
        string="Survey URL",
    )

    def _compute_survey_count(self):
        for record in self:
            record.survey_count = len(record.survey_ids)

    def action_view_surveys(self):
        action = self.env.ref("survey.action_survey_user_input").read()[0]
        action["domain"] = [("sale_id", "=", self.id)]
        return action

    @api.multi
    def _compute_survey_url(self):
        default_survey_id = self.env["survey.survey"].search(
            [
                ("default_sale_survey", "=", True),
            ]
        )
        base_url = self.env["ir.config_parameter"].get_param("web.base.url")
        if not default_survey_id:
            raise UserError(_("There is no default survey for sale orders."))
        for record in self:
            vals = {
                "survey_id": default_survey_id.id,
                "partner_id": record.partner_id.id,
                "sale_id": record.id,
                "type": "link",
            }
            survey_user_input = self.env["survey.user_input"].create(vals)
            survey_url = base_url + "/survey/fill/%s/%s" % (
                slug(default_survey_id),
                survey_user_input.token,
            )
            if default_survey_id.url_shortener_id:
                record.survey_url = default_survey_id.url_shortener_id.shorten_url(
                    survey_url
                )
            else:
                record.survey_url = survey_url
