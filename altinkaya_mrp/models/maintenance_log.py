from odoo import fields, models


class MaintenanceLog(models.Model):
    _name = "maintenance.log"
    _description = "Maintenance Log"
    _order = "create_date desc, id desc"

    product_id = fields.Many2one(
        "product.product",
        string="Product",
        required=True,
        ondelete="cascade",
        index=True,
    )
    note = fields.Text(string="Note")
    photo = fields.Image(string="Photo")
    duration = fields.Float(string="Duration")
    duration_uom_id = fields.Many2one(
        "uom.uom",
        string="Duration UoM",
        domain=lambda self: [
            ("category_id", "=", self.env.ref("uom.uom_categ_wtime").id)
        ],
    )
    performed_by_id = fields.Many2one("hr.employee", string="Performed By")
    # created_by = create_uid, date = create_date (automatic)
