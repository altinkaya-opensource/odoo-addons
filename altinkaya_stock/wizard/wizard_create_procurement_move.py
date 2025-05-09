#
# Created on Oct 12, 2018
#
# @author: dogan
#

from odoo import api, fields, models
from odoo.tools.misc import clean_context


class CreateProcurementMove(models.TransientModel):
    _name = "create.procurement.move"
    _description = "Create procurement move"

    move_id = fields.Many2one("stock.move", "Move", readonly=True)
    product_id = fields.Many2one(
        "product.product", string="Product", related="move_id.product_id", readonly=True
    )

    move_qty = fields.Float(
        "Demand Quantity", related="move_id.product_uom_qty", readonly=True
    )
    procure_move = fields.Boolean("Harekete Tedarik Oluştur", default=True)
    uom = fields.Many2one(
        "uom.uom", string="UoM", related="move_id.product_uom", readonly=True
    )

    qty_to_sincan = fields.Float("Tedarik Sincan")
    qty_to_merkez = fields.Float("Tedarik Merkez")
    qty_available_merkez = fields.Float(
        "Merkez Mevcut", related="product_id.qty_available_merkez"
    )
    qty_available_sincan = fields.Float(
        "Sincan Mevcut", related="product_id.qty_available_sincan"
    )
    qty_incoming_merkez = fields.Float(
        "Gelen Merkez", related="product_id.qty_incoming_merkez"
    )
    qty_incoming_sincan = fields.Float(
        "Gelen Sincan", related="product_id.qty_incoming_sincan"
    )
    qty_outgoing_merkez = fields.Float(
        "Giden Merkez", related="product_id.qty_outgoing_merkez"
    )
    qty_outgoing_sincan = fields.Float(
        "Giden Sincan", related="product_id.qty_outgoing_sincan"
    )
    qty_virtual_merkez = fields.Float(
        "Tahmini Merkez", related="product_id.qty_virtual_merkez"
    )
    qty_virtual_sincan = fields.Float(
        "Tahmini Sincan", related="product_id.qty_virtual_sincan"
    )

    production_ids = fields.Many2many(
        "mrp.production", string="Manufacturing Orders", compute="_compute_productions"
    )
    transfers_to_customer_ids = fields.Many2many(
        "stock.move",
        string="Transfers to Customers",
        compute="_compute_customer_transfers",
    )
    pending_orderline_ids = fields.Many2many(
        "sale.order.line",
        string="Pending Orders",
        compute="_compute_pending_orderlines",
    )

    sale_qty30days = fields.Float(
        "Son 1 ayda satılan",
        related="move_id.product_id.sale_qty30days",
        readonly=True,
        store=False,
    )
    sale_qty180days = fields.Float(
        "Son 6 ayda satılan",
        related="move_id.product_id.sale_qty180days",
        readonly=True,
        store=False,
    )
    sale_qty360days = fields.Float(
        "Son 1 senede satılan",
        related="move_id.product_id.sale_qty360days",
        readonly=True,
        store=False,
    )

    @api.depends("product_id")
    def _compute_productions(self):
        for wizard in self:
            wizard.production_ids = self.env["mrp.production"].search(
                [
                    ("product_id", "=", wizard.product_id.id),
                    ("state", "not in", ["done", "cancel"]),
                ],
                limit=40,
                order="create_date desc",
            )

    @api.depends("product_id")
    def _compute_customer_transfers(self):
        for wizard in self:
            wizard.transfers_to_customer_ids = self.env["stock.move"].search(
                [
                    ("product_id", "=", wizard.product_id.id),
                    ("state", "not in", ["draft", "done", "cancel"]),
                ],
                limit=40,
                order="create_date desc",
            )

    @api.depends("product_id")
    def _compute_pending_orderlines(self):
        for wizard in self:
            wizard.pending_orderline_ids = self.env["sale.order.line"].search(
                [
                    ("product_id", "=", wizard.product_id.id),
                    ("state", "not in", ["draft", "done", "cancel"]),
                ],
                limit=40,
                order="create_date desc",
            )

    def action_create(self):
        self.ensure_one()
        if self.move_id.state == "cancel":
            self.move_id.write({"state": "draft", "procure_method": "make_to_stock"})
            self.move_id._action_confirm()

        if self.procure_move:
            self.create_procurement(
                group_id=self.move_id.group_id,
                location_id=self.move_id.location_id,
                qty=self.move_id.product_uom_qty,
            )

            self.move_id._do_unreserve()
            self.move_id.procure_method = "make_to_order"
            self.move_id.write({"state": "waiting"})

        if self.qty_to_sincan > 0.0:
            self.create_replenishment(location_id=21, qty=self.qty_to_sincan)

        if self.qty_to_merkez > 0.0:
            self.create_replenishment(location_id=12, qty=self.qty_to_merkez)

    def create_replenishment(self, location_id, qty):
        """
        Create a replenishment with new procurement group
        """
        self.ensure_one()
        location_id = self.env["stock.location"].browse(location_id)
        warehouse = location_id.warehouse_id
        group_id = self.env["procurement.group"].create(
            {
                "name": f"{warehouse.name} Manuel: {self.env.user.name}",
            }
        )

        values = {
            "group_id": group_id,
            "warehouse_id": warehouse,
        }
        product_qty = qty
        product_uom = self.uom
        origin = "Manuel" + str(self.env.user.id)
        self.env["procurement.group"].with_context(clean_context(self.env.context)).run(  # pylint: disable=W8121
            [
                self.env["procurement.group"].Procurement(
                    self.product_id,
                    product_qty,
                    product_uom,
                    warehouse.lot_stock_id,  # Location
                    origin,  # Name
                    origin,  # Origin
                    warehouse.company_id,
                    values,  # Values
                )
            ]
        )

    def create_procurement(self, group_id, location_id, qty):
        """
        Create a procurement with current procurement group
        """
        self.ensure_one()
        warehouse = location_id.warehouse_id
        if not group_id:
            group_id = self.env["procurement.group"].create(
                {
                    "name": warehouse.name + " Açan: " + self.env.user.name,
                }
            )
        values = {
            "date_planned": self.move_id.date_deadline
            or self.move_id.forecast_expected_date,
            "group_id": group_id,
            "warehouse_id": warehouse,
            "move_dest_ids": self.move_id,
        }
        if not values["date_planned"]:
            values.pop("date_planned")

        product_qty = qty
        product_uom = self.uom
        origin = self.move_id.origin or "/"

        self.env["procurement.group"].with_context(clean_context(self.env.context)).run(  # pylint: disable=W8121
            [
                self.env["procurement.group"].Procurement(
                    self.product_id,
                    product_qty,
                    product_uom,
                    warehouse.lot_stock_id,  # Location
                    origin,  # Name
                    origin,  # Origin
                    warehouse.company_id,
                    values,  # Values
                )
            ]
        )
