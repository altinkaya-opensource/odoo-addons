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
                        "checked (%(title)s). Please uncheck it before "
                        "checking this survey.",
                        title=exist_default.title,
                    )
                )

    @api.depends(
        "user_input_ids.state",
        "user_input_ids.test_entry",
        "user_input_ids.scoring_percentage",
        "user_input_ids.scoring_success",
    )
    def _compute_survey_statistic(self):
        # super()._compute_survey_statistic()
        default_vals = {
            "answer_count": 0,
            "answer_done_count": 0,
            "success_count": 0,
            "answer_score_avg": 0.0,
            "success_ratio": 0.0,
        }
        stat = dict(
            (cid, dict(default_vals, answer_score_avg_total=0.0)) for cid in self.ids
        )
        UserInput = self.env["survey.user_input"]
        base_domain = [("survey_id", "in", self.ids)]

        read_group_res = UserInput._read_group(
            base_domain,
            ["survey_id", "state"],
            ["survey_id", "state", "scoring_percentage", "scoring_success"],
            lazy=False,
        )
        for item in read_group_res:
            stat[item["survey_id"][0]]["answer_count"] += item["__count"]
            stat[item["survey_id"][0]]["answer_score_avg_total"] += item[
                "scoring_percentage"
            ]
            if item["state"] == "done":
                stat[item["survey_id"][0]]["answer_done_count"] += item["__count"]
            if item["scoring_success"]:
                stat[item["survey_id"][0]]["success_count"] += item["__count"]

        for survey_stats in stat.values():
            avg_total = survey_stats.pop("answer_score_avg_total")
            survey_stats["answer_score_avg"] = avg_total / (
                survey_stats["answer_done_count"] or 1
            )
            survey_stats["success_ratio"] = (
                survey_stats["success_count"]
                / (survey_stats["answer_done_count"] or 1.0)
            ) * 100

        for survey in self:
            survey.update(stat.get(survey._origin.id, default_vals))
