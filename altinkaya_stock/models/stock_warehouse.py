from odoo import fields, models


class Warehouse(models.Model):
    _inherit = "stock.warehouse"

    selectable_on_procurement_wizard = fields.Boolean(
        "Selectable on procurement wizard"
    )
