from odoo import fields, models


class IrAttachment(models.Model):
    _inherit = "ir.attachment"

    is_delivery_document = fields.Boolean()
