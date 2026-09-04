import base64

from odoo import api, fields, models


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
    qr_code = fields.Binary(compute="_compute_qr_code", string="QR Code")
    # created_by = create_uid, date = create_date (automatic)

    @api.depends("product_id.barcode")
    def _compute_qr_code(self):
        # The product's GS1 Digital Link QR, so a saved log can be scanned from
        # the mobile maintenance applet. Rendered through the same barcode engine
        # the SOP procedure sheet uses. No-op without a product barcode.
        for rec in self:
            rec.qr_code = False
            product = rec.product_id
            if not (product and product.barcode):
                continue
            url = self.env["gs1.digital.link"].build_product_link(product.barcode)
            img = self.env["ir.actions.report"].barcode(
                "QR", url, width=200, height=200
            )
            rec.qr_code = base64.b64encode(img)
