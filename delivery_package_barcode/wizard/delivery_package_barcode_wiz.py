# Copyright 2022 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo import _, api, fields, models


class DeliveryPackageBarcodeWiz(models.TransientModel):
    _name = "delivery.package.barcode.wiz"
    _inherit = "barcodes.barcode_events_mixin"
    _description = "Wizard to read barcode for delivery package"
    # To prevent remove the record wizard until 2 days old
    _transient_max_hours = 48

    name = fields.Char()
    message = fields.Char(default="Scan a barcode", readonly=1)
    message_type = fields.Selection(
        [("success", "Success"), ("error", "Error"), ("info", "Info")], default="info"
    )
    barcode = fields.Char()
    picking_id = fields.Many2one(
        comodel_name="stock.picking",
    )
    picking_line_ids = fields.One2many(
        "stock.move",
        string="Picking Lines",
        related="picking_id.move_ids_without_package",
    )
    package_count = fields.Integer(default=0)
    package_weight = fields.Float(default=0.0)

    @api.onchange("picking_id")
    def onchange_picking_id(self):
        self.update(
            {
                "package_count": self.picking_id.carrier_package_count,
                "package_weight": self.picking_id.picking_total_weight,
            }
        )

    @api.model
    def create(self, vals_list):
        res = super(DeliveryPackageBarcodeWiz, self).create(vals_list)
        if not res.name:
            res.name = res.picking_id.name + _(" - PACK BARCODE")
        return res

    def button_save(self):
        vals = {
            "carrier_package_count": self.package_count,
            "picking_total_weight": self.package_weight,
            "is_packaged": True,
        }
        self.picking_id.write(vals)
        return True

    def process_barcode(self, barcode):
        pick_obj = self.env["stock.picking"]

        if barcode and self.env.user.has_group("stock.group_stock_user"):
            domain = self._barcode_domain(barcode)
            picking = pick_obj.search(domain, limit=1)
            if picking:
                self.update(
                    {
                        "picking_id": picking.id,
                        "message": _("Picking found:"),
                        "message_type": "success",
                    }
                )
            else:
                self.update(
                    {
                        "message": _("Picking not found"),
                        "message_type": "error",
                    }
                )
        return

    def _barcode_domain(self, barcode):
        return [
            "|",
            "|",
            ("name", "=", barcode),
            ("shipping_number", "=", barcode),
            ("carrier_tracking_ref", "=", barcode),
        ]

    def on_barcode_scanned(self, barcode):
        self.barcode = barcode
        self.process_barcode(self.barcode)
