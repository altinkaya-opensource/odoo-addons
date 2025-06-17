# Copyright 2023 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SurveySurvey(models.Model):
    _inherit = "survey.survey"

    default_sale_survey = fields.Boolean(
        string="Sale Survey",
        help="If checked, this survey will be used as default survey for sale orders.",
    )
    default_partner_survey = fields.Boolean(
        string="Partner Survey",
        help="If checked, this survey will be used as default survey for partner.",
    )
    default_invoice_survey = fields.Boolean(
        string="Invoice Survey",
        help="If checked, this survey will be used as default survey for invoices.",
    )
    # default_lang_id = fields.Many2one(
    #     comodel_name="res.lang",
    #     string="Default Language",
    #     help="Default language for survey",
    #     required=True,
    #     domain=[("active", "=", True)],
    # )

    url_shortener_id = fields.Many2one(
        "short.url.yourls",
        string="URL Shortener",
        help="If set, survey url will be shortened using this shortener.",
    )

    @api.constrains("default_sale_survey", "default_partner_survey")
    def _check_default_sale_survey(self):
        """
        Check if there is only one survey with default surveys checked.
        :return: None
        """
        domain = [("id", "!=", self.id)]
        if self.default_sale_survey:
            domain += [("default_sale_survey", "=", True)]
        elif self.default_partner_survey:
            domain += [("default_partner_survey", "=", True)]
        elif self.default_invoice_survey:
            domain += [("default_invoice_survey", "=", True)]

        if (
            self.default_sale_survey
            or self.default_partner_survey
            or self.default_invoice_survey
        ):
            exist_default = self.search(domain)
            if exist_default:
                raise UserError(
                    _(
                        "There is already a survey with default sale survey "
                        "checked (%(title)s). Please uncheck it before checking "
                        "this survey.",
                        title=exist_default.title,
                    )
                )
