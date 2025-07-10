from odoo import fields, models


class TableGenerator(models.Model):
    _name = "table.generator"
    _description = "Dynamic Table Generator"

    table_name = fields.Char(required=True)
    table_model_id = fields.Many2one(
        "ir.model", string="Model", required=True, ondelete="cascade"
    )
    table_field_id = fields.Many2many(
        "ir.model.fields",
        string="Fields of table",
        domain="[('model_id', '=', table_model_id)]",
        ondelete="cascade",
        required=True,
    )

    def action_generate_table(self):
        for rec in self:
            selected_field_names = rec.table_field_id.mapped("name")
            all_data = self.env[rec.table_model_id.model].search([])

            dynamic_data = []
            for record in all_data:
                row = {field: getattr(record, field) for field in selected_field_names}
                dynamic_data.append(row)
            return dynamic_data

    def get_all_tables(self):
        all_tables = self.search([])
        prepared_table = []
        for table in all_tables:
            getdata = table.action_generate_table()
            prepared_table.append(getdata)

        return prepared_table
