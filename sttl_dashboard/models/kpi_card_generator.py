import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class KpiCardGenerator(models.Model):
    _name = "kpi.card.generator"
    _description = "Dynamic Kpi-Card Generator"

    kpi_card_name = fields.Char("Card Name", required=True)
    kpi_title_description = fields.Char("Title description", required=True)
    kpi_description = fields.Char("Small descrption", required=True)
    kpi_color = fields.Char("Color")
    kpi_model_id = fields.Many2one(
        "ir.model", string="Model", required=True, ondelete="cascade"
    )
    kpi_unique_id = fields.Integer(string="Unique Id")
    kpi_aggregate = fields.Selection(
        [("count", "Count"), ("sum", "Sum"), ("avg", "Avg")], string="Aggregate"
    )
    kpi_field_aggregate = fields.Many2one(
        "ir.model.fields",
        string="Aggregate field",
        domain="[('model_id','=',kpi_model_id),('name','!=','id'),('store','=',True),'|',"
        "'|',('ttype','=','integer'),('ttype','=','float'),"
        "('ttype','=','monetary')]",
        ondelete="cascade",
    )
    kpi_size = fields.Selection([("half", "Half"), ("fit", "Fit")], string="kpi size")
    dashboard_sequence_number = fields.Integer(string="Sequence", default=10)

    def action_generate_kpi(self):
        return {
            "type": "ir.actions.client",
            "tag": "reload",
        }

    def kpi_card_processing(self):
        for rec in self:
            model_name = self.env[rec.kpi_model_id.model]
            data_dict = {}
            if rec.kpi_aggregate == "count":
                try:
                    data = model_name.read_group([], [], [])
                    if len(data) > 0:
                        if data[0]["__count"]:
                            data_dict["aggregate"] = data[0]["__count"]
                except Exception:
                    _logger.error(
                        "Error occurred while fetching count aggregate", exc_info=True
                    )
            else:
                try:
                    data = model_name.read_group(
                        [], [f"{rec.kpi_field_aggregate.name}:{rec.kpi_aggregate}"], []
                    )
                    if len(data) > 0:
                        if data[0][rec.kpi_field_aggregate.name]:
                            data_dict["aggregate"] = data[0][
                                rec.kpi_field_aggregate.name
                            ]

                except Exception:
                    _logger.error(
                        "Error occurred while fetching aggregate for field %s",
                        rec.kpi_field_aggregate.name,
                        exc_info=True,
                    )

            data_dict["name"] = rec.kpi_card_name
            data_dict["id"] = rec.id
            return data_dict

    def get_all_kpi_cards(self, domain=None):
        all_kpi_cards = []
        domain = [("kpi_unique_id", "=", domain)] or []
        records = self.search(domain)
        for rec in records:
            single_kpi_card = rec.kpi_card_processing()
            single_kpi_card["type"] = "kpi"
            single_kpi_card["dashboard_sequence_number"] = rec.dashboard_sequence_number
            single_kpi_card["model"] = rec.kpi_model_id.model
            single_kpi_card["size"] = rec.kpi_size
            single_kpi_card["description"] = rec.kpi_description
            single_kpi_card["name"] = rec.kpi_card_name
            single_kpi_card["id"] = rec.id
            single_kpi_card["title_description"] = rec.kpi_title_description
            single_kpi_card["kpi_color"] = rec.kpi_color
            all_kpi_cards.append(single_kpi_card)
        return all_kpi_cards
