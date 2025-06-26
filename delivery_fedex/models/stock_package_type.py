from odoo import fields, models


class ProductPackaging(models.Model):
    _inherit = "stock.package.type"

    package_carrier_type = fields.Selection(
        selection_add=[("fedex", "FedEx")], ondelete={"fedex": "cascade"}
    )
