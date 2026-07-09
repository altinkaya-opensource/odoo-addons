from odoo import fields, models


class MaintenanceLog(models.Model):
    _name = "maintenance.log"
    _description = "Maintenance Log"
    _order = "create_date desc, id desc"

    product_id = fields.Many2one(
        "product.product",
        required=True,
        ondelete="cascade",
        index=True,
    )
    note = fields.Text()
    photo = fields.Image()
    duration = fields.Float()
    duration_uom_id = fields.Many2one(
        "uom.uom",
        string="Duration UoM",
        domain=lambda self: [
            ("category_id", "=", self.env.ref("uom.uom_categ_wtime").id)
        ],
    )
    performed_by_id = fields.Many2one("hr.employee")
    # created_by = create_uid, date = create_date (automatic)
