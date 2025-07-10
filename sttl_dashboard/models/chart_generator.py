import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.safe_eval import safe_eval

_logger = logging.getLogger(__name__)


class ChartGenerator(models.Model):
    _name = "chart.generator"
    _description = "Dynamic Chart Generator"

    dashboard_chart_type = fields.Selection(
        [
            ("bar", "Bar"),
            ("pie", "Pie"),
            ("bubble", "Bubble"),
            ("doughnut", "Doughnut"),
            ("line", "Line"),
            ("polarArea", "polar area"),
        ],
        required=True,
        string="Chart",
    )
    dashboard_name = fields.Char(string="Chart Name", required=True)
    dashboard_aggregate = fields.Selection(
        [("count", "Count"), ("sum", "Sum"), ("avg", "Avg")],
        string="Aggregate",
        required=True,
    )
    dashboard_field_aggregate = fields.Many2one(
        "ir.model.fields",
        string="Aggregate field",
        domain="[('model_id','=',dashboard_model_id),('name','!=','id'),('store','=',True),'|',"
        "'|',('ttype','=','integer'),('ttype','=','float'),"
        "('ttype','=','monetary')]",
        ondelete="cascade",
    )
    dashboard_model_id = fields.Many2one(
        "ir.model", string="Model", required=True, ondelete="cascade"
    )
    dashboard_field_id = fields.Many2one(
        "ir.model.fields",
        string="Group By Field",
        domain="[('model_id', '=', dashboard_model_id),('name','!=','id'),"
        "('name','!=','sequence'),"
        "('store','=',True),('ttype','!=','binary'),"
        "('ttype','!=','many2many'), ('ttype','!=','one2many')]",
        ondelete="cascade",
        required=True,
    )
    dashboard_unique_id = fields.Integer(string="Unique Id")
    dashboard_limit_value = fields.Integer(string="Limit")
    dashboard_sort_by = fields.Selection(
        [("ASC", "Ascending"), ("DESC", "Descending")], string="Chart Sort By"
    )
    dashboard_domain = fields.Char(string="Domain")
    dashboard_sequence_number = fields.Integer(string="Sequence of chart", default=10)

    def parse_domain_string(self, domain_str):
        try:
            list_str = safe_eval(domain_str)
        except ValueError:
            raise UserError(_("Invalid Domain"))
        return list_str

    @api.onchange("dashboard_model_id")
    def empty_field_and_fieldaggregate(self):
        for rec in self:
            if rec.dashboard_field_id:
                rec.dashboard_field_id = False
            if rec.dashboard_field_aggregate:
                rec.dashboard_field_aggregate = False

    @api.model
    def create(self, vals):
        domain_string = vals.get("dashboard_domain")
        if domain_string:
            model_id = self.env["ir.model"].browse(vals.get("dashboard_model_id"))
            field_id = self.env["ir.model.fields"].browse(
                vals.get("dashboard_field_id")
            )
            model_name = self.env[model_id.model]
            field_name = field_id.name
            Domain = self.parse_domain_string(domain_string)
            try:
                model_name.read_group(Domain, [field_name], [field_name])
            except:  # noqa: E722
                raise UserError(_("Invalid Domain"))
        return super().create(vals)

    def write(self, vals):
        if vals.get("dashboard_domain"):
            for rec in self:
                model_name = self.env[rec.dashboard_model_id.model]
                field_name = rec.dashboard_field_id.name
                Domain = self.parse_domain_string(vals.get("dashboard_domain"))
                try:
                    model_name.read_group(Domain, [field_name], [field_name])
                except:  # noqa: E722
                    raise UserError(_("Invalid Domain"))

        return super().write(vals)

    def action_generate_chart(self):
        return {
            "type": "ir.actions.client",
            "tag": "reload",
        }

    def get_chart_data_for_get_all_charts(self):  # noqa E501
        for rec in self:
            model_name = self.env[rec.dashboard_model_id.model]
            field_name = rec.dashboard_field_id.name
            domain = []
            chart_data = {}
            if self.dashboard_domain:
                domain = self.parse_domain_string(self.dashboard_domain)
            try:
                if rec.dashboard_aggregate == "count":
                    get_count_name = field_name + "_count"
                    if (
                        rec.dashboard_field_id.ttype == "date"
                        or rec.dashboard_field_id.ttype == "datetime"
                    ):
                        data = model_name.read_group(
                            domain, [field_name], [f"{field_name}:day"]
                        )
                        for record in data:
                            record[field_name] = record.pop(f"{field_name}:day")
                    else:
                        data = model_name.read_group(domain, [field_name], [field_name])
                    if rec.dashboard_sort_by == "DESC":
                        if rec.dashboard_limit_value != 0:
                            sorted_data = sorted(
                                data, key=lambda x: x[get_count_name], reverse=True
                            )[: rec.dashboard_limit_value]
                            data = sorted_data
                        else:
                            sorted_data = sorted(
                                data, key=lambda x: x[get_count_name], reverse=True
                            )
                            data = sorted_data

                    elif rec.dashboard_sort_by == "ASC":
                        if rec.dashboard_limit_value != 0:
                            sorted_data = sorted(data, key=lambda x: x[get_count_name])[
                                : rec.dashboard_limit_value
                            ]
                            data = sorted_data
                        else:
                            sorted_data = sorted(data, key=lambda x: x[get_count_name])
                            data = sorted_data
                    else:
                        if rec.dashboard_limit_value != 0:
                            sorted_data = sorted(data, key=lambda x: x[get_count_name])[
                                : rec.dashboard_limit_value
                            ]
                            data = sorted_data

                    chart_data = {
                        "labels": [
                            entry[field_name][1]
                            if isinstance(entry[field_name], tuple)
                            else entry[field_name]
                            for entry in data
                        ],
                        "datasets": [
                            {
                                "label": rec.dashboard_name,
                                "data": [entry[get_count_name] for entry in data],
                            }
                        ],
                        "model_name": rec.dashboard_model_id.model,
                        "field_name": field_name,
                    }
                else:
                    aggregate_field_name = rec.dashboard_field_aggregate.name

                    if rec.dashboard_sort_by:
                        if (
                            rec.dashboard_field_id.ttype == "date"
                            or rec.dashboard_field_id.ttype == "datetime"
                        ):
                            agg_data = model_name.read_group(
                                domain,
                                [
                                    field_name,
                                    f"{aggregate_field_name}:{rec.dashboard_aggregate}",
                                ],
                                [f"{field_name}:day"],
                                limit=rec.dashboard_limit_value,
                                orderby=(
                                    f"{aggregate_field_name} "
                                    f"{rec.dashboard_sort_by}"
                                ),
                            )
                            for record in agg_data:
                                record[field_name] = record.pop(f"{field_name}:day")
                        else:
                            agg_data = model_name.read_group(
                                domain,
                                [
                                    field_name,
                                    f"{aggregate_field_name}:{rec.dashboard_aggregate}",
                                ],
                                [field_name],
                                limit=rec.dashboard_limit_value,
                                orderby=(
                                    f"{aggregate_field_name} "
                                    f"{rec.dashboard_sort_by}"
                                ),
                            )
                    else:
                        if rec.dashboard_field_id.ttype == "date":
                            agg_data = model_name.read_group(
                                domain,
                                [
                                    field_name,
                                    f"{aggregate_field_name}:{rec.dashboard_aggregate}",
                                ],
                                [f"{field_name}:day"],
                                limit=rec.dashboard_limit_value,
                                orderby=f"{aggregate_field_name}",
                            )
                            for record in agg_data:
                                record[field_name] = record.pop(f"{field_name}:day")
                        else:
                            agg_data = model_name.read_group(
                                domain,
                                [
                                    field_name,
                                    f"{aggregate_field_name}:{rec.dashboard_aggregate}",
                                ],
                                [field_name],
                                limit=rec.dashboard_limit_value,
                                orderby=f"{aggregate_field_name}",
                            )

                    chart_data = {
                        "labels": [
                            entry[field_name][1]
                            if isinstance(entry[field_name], tuple)
                            else entry[field_name]
                            for entry in agg_data
                        ],
                        "datasets": [
                            {
                                "label": rec.dashboard_name,
                                "data": [
                                    entry[aggregate_field_name] for entry in agg_data
                                ],
                            }
                        ],
                        "model_name": rec.dashboard_model_id.model,
                        "field_name": field_name,
                    }
            except Exception as e:
                _logger.error("Error generating chart data: %s", e)
            return chart_data

    def get_all_charts_data(self, domain=None):
        all_charts_data = []

        domain = [("dashboard_unique_id", "=", domain)] or []

        records = self.search(domain)
        try:
            for rec in records:
                chart_data = rec.get_chart_data_for_get_all_charts()
                if chart_data:
                    chart_data["id"] = rec.id
                    chart_data["chart_name"] = rec.dashboard_name
                    chart_data["chart_type"] = rec.dashboard_chart_type
                    chart_data["dashboard_sequence_number"] = (
                        rec.dashboard_sequence_number
                    )
                    chart_data["type"] = "chart"
                    all_charts_data.append(chart_data)

            return all_charts_data
        except Exception as e:
            _logger.error("Error fetching chart data: %s", e)
            return []
