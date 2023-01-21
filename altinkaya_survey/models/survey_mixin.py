# Copyright 2023 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo import models, api, fields, _
from odoo.exceptions import UserError
from odoo.addons.http_routing.models.ir_http import slug
import base64

model_field_mapping = {
    "sale.order": "sale_id",
    "account.invoice": "invoice_id",
    "res.partner": "partner_id",
}


class SurveyMapping(models.AbstractModel):
    _name = "survey.mapping"
    _description = "Base model for Survey - Odoo models integration"

    survey_ids = fields.One2many(
        comodel_name="survey.user_input",
        store=False,
        compute="_compute_survey_ids",
        string="Surveys",
    )

    survey_count = fields.Integer(
        string="Survey Count",
        store=False,
        compute="_compute_survey_count",
    )

    survey_url = fields.Char(
        compute="_compute_survey_url",
        string="Survey URL",
    )

    survey_url_qr = fields.Char(
        "Survey URL QR",
        compute="_compute_survey_url_qr",
    )

    @api.depends("survey_ids")
    def _compute_survey_count(self):
        for rec in self:
            rec.survey_count = len(rec.survey_ids)

    @api.model
    def _compute_survey_ids(self):
        """Compute survey_ids field"""
        for record in self:
            record.survey_ids = self.env["survey.user_input"].search(
                [
                    (model_field_mapping[record._name], "=", record.id),
                ]
            )

    def action_view_surveys(self):
        """Open survey list view for active record"""

        action = self.env.ref("survey.action_survey_user_input").read()[0]
        action["domain"] = [(model_field_mapping[self._name], "=", self.id)]
        return action

    @api.multi
    def _compute_survey_url(self):
        """Base method for computing survey url. This method is overridden in
        models that inherit from this mixin."""
        raise NotImplementedError

    def _get_default_survey(self, default_field):
        """Check if survey is default survey. If it is, raise an error"""
        default_survey_id = self.env["survey.survey"].search(
            [
                (default_field, "=", True),
            ]
        )
        if not default_survey_id:
            raise UserError(_("There is no default survey for partners."))
        return default_survey_id

    def _get_base_url(self):
        """Get base url for survey url"""
        return self.env["ir.config_parameter"].sudo().get_param("web.base.url")

    def _create_survey_url(self, vals, survey):
        """Create survey url for active record"""
        base_url = self._get_base_url()
        survey_user_input = self.env["survey.user_input"].create(vals)
        survey_url = base_url + "/%s/survey/fill/%s/%s" % (
            survey.default_lang_id.code or "tr_TR",
            slug(survey),
            survey_user_input.token,
        )
        if survey.url_shortener_id:
            survey_url = survey.url_shortener_id.shorten_url(survey_url)
        else:
            survey_url = survey_url
        return survey_url

    @api.multi
    def _compute_survey_url_qr(self):
        """Compute survey url qr code for active record"""
        for rec in self:
            barcode = self.env["ir.actions.report"].barcode(
                "QR",
                value=rec.survey_url,
                width=300,
                height=300,
            )
            rec.survey_url_qr = base64.b64encode(barcode)


class SurveyResPartnerMixin(models.Model):
    _name = "res.partner"
    _inherit = ["res.partner", "survey.mapping"]

    @api.multi
    def _compute_survey_url(self):
        default_survey_id = self._get_default_survey("default_partner_survey")
        for record in self:
            vals = {
                "survey_id": default_survey_id.id,
                "partner_id": record.id,
                "type": "link",
            }
            record.survey_url = self._create_survey_url(vals, default_survey_id)


class SurveySaleOrderMixin(models.Model):
    _name = "sale.order"
    _inherit = ["sale.order", "survey.mapping"]

    def _compute_survey_url(self):
        default_survey_id = self._get_default_survey("default_sale_survey")
        for record in self:
            vals = {
                "survey_id": default_survey_id.id,
                "partner_id": record.partner_id.id,
                "sale_id": record.id,
                "type": "link",
            }
            record.survey_url = self._create_survey_url(vals, default_survey_id)
