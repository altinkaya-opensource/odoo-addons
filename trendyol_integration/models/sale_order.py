# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import _, fields, models
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = "sale.order"

    trendyol_binding_ids = fields.One2many(
        "trendyol.order",
        "odoo_id",
        string="Trendyol Orders",
    )
    trendyol_order_number = fields.Char(
        string="Trendyol Order Number",
        related="trendyol_binding_ids.trendyol_order_number",
    )
    trendyol_status = fields.Selection(
        related="trendyol_binding_ids.trendyol_status",
        string="Trendyol Status",
    )

    def action_cancel(self):
        """Block direct cancellation of Trendyol orders.

        Users must cancel from the Trendyol Orders section so the
        cancellation is propagated to the Trendyol API first.
        """
        trendyol_orders = self.filtered(
            lambda o: (
                o.trendyol_binding_ids and o.trendyol_status not in (False, "cancelled")
            )
        )
        if trendyol_orders and not self.env.context.get("from_trendyol_cancel"):
            raise UserError(
                _(
                    "This order was created from Trendyol. Please cancel it"
                    " from the Trendyol Orders section first so the"
                    " cancellation is sent to Trendyol."
                )
            )
        return super().action_cancel()

    def action_view_trendyol_binding(self):
        """View Trendyol binding for this order."""
        self.ensure_one()
        binding = self.trendyol_binding_ids[:1]
        if binding:
            return {
                "type": "ir.actions.act_window",
                "name": "Trendyol Order",
                "res_model": "trendyol.order",
                "view_mode": "form",
                "res_id": binding.id,
            }
        return False
