#
# Created on Jan 17, 2020
#
# @author: dogan
#
from odoo import api, fields, models


class StockWarehouseOrderpoint(models.Model):
    _inherit = "stock.warehouse.orderpoint"

    transfers_to_customer_ids = fields.Many2many(
        "stock.move",
        string="Transfers to Customers",
        compute="_compute_customer_transfers",
    )

    production_ids = fields.Many2many(
        "mrp.production", string="Manufacturing Orders", compute="_compute_productions"
    )

    done_purchaseline_ids = fields.Many2many(
        "purchase.order.line",
        string="Previous Purchases",
        compute="_compute_done_purchaselines",
    )

    done_orderline_ids = fields.Many2many(
        "sale.order.line", string="Done Orders", compute="_compute_done_orderlines"
    )

    def _get_product_context(self, visibility_days=0):
        """Inherited to add included_location_ids on stock.location model."""
        res = super()._get_product_context(visibility_days)
        res["location_id"] = [
            self.location_id.id,
            *self.location_id.included_location_ids.ids,
        ]
        return res

    def _compute_productions(self):
        for orderpoint in self:
            orderpoint.production_ids = self.env["mrp.production"].search(
                [
                    ("product_id", "=", orderpoint.product_id.id),
                    ("state", "not in", ["cancel"]),
                ],
                order="create_date desc",
            )

    def _compute_customer_transfers(self):
        for orderpoint in self:
            orderpoint.transfers_to_customer_ids = self.env["stock.move"].search(
                [
                    ("product_id", "=", orderpoint.product_id.id),
                    ("state", "not in", ["draft", "cancel"]),
                ],
                order="create_date desc",
            )

    def _compute_done_purchaselines(self):
        for orderpoint in self:
            orderpoint.done_purchaseline_ids = self.env["purchase.order.line"].search(
                [
                    ("product_id", "=", orderpoint.product_id.id),
                    ("state", "not in", ["draft", "cancel"]),
                ],
                limit=40,
                order="create_date desc",
            )

    def _compute_done_orderlines(self):
        for orderpoint in self:
            orderpoint.done_orderline_ids = self.env["sale.order.line"].search(
                [
                    ("product_id", "=", orderpoint.product_id.id),
                    ("state", "not in", ["draft", "cancel"]),
                ],
                order="create_date desc",
            )
