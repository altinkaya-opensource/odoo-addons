from odoo import fields, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    internal_note = fields.Text(
        string="Internal Note",
        help="Internal note for the order. This field is not visible to the customer.",
    )