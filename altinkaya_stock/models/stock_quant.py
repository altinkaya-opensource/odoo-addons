import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare, float_is_zero

_logger = logging.getLogger(__name__)


class StockQuant(models.Model):
    _inherit = "stock.quant"

    categ_id = fields.Many2one(
        "product.category",
        string="Category",
        related="product_id.product_tmpl_id.categ_id",
        readonly=True,
        store=True,
    )

    priority = fields.Integer(
        related="location_id.priority",
        help="high priority quants will be reserved first",
        readonly=True,
        store=True,
    )

    def action_show_reserved_moves(self):
        action = self.env.ref("altinkaya_stock.stock_move_line_action").read()[0]
        action["domain"] = [
            ("move_line_ids.location_id", "=", self.location_id.id),
            ("product_id", "=", self.product_id.id),
        ]
        return action

    @api.model
    def _get_removal_strategy_order(self, removal_strategy):
        if removal_strategy == "priorityfifo":
            return "priority, in_date ASC, id"
        return super()._get_removal_strategy_order(removal_strategy)

    @api.model
    def _update_reserved_quantity(
        self,
        product_id,
        location_id,
        quantity,
        lot_id=None,
        package_id=None,
        owner_id=None,
        strict=False,
    ):
        """Cap unreserve to what is actually reserved on matching quants."""
        rounding = product_id.uom_id.rounding
        if float_compare(quantity, 0, precision_rounding=rounding) < 0:
            quants = self.sudo()._gather(
                product_id,
                location_id,
                lot_id=lot_id,
                package_id=package_id,
                owner_id=owner_id,
                strict=strict,
            )
            negative_quants = quants.filtered(
                lambda quant: (
                    float_compare(
                        quant.reserved_quantity, 0, precision_rounding=rounding
                    )
                    < 0
                )
            )
            if negative_quants:
                _logger.warning(
                    "Skipping unreserve of %s of %s at %s because quants %s have "
                    "negative reserved quantities",
                    abs(quantity),
                    product_id.display_name,
                    location_id.display_name,
                    negative_quants.ids,
                )
                self._raise_fix_unreserve_action(product_id)
                raise UserError(
                    _(
                        "It is not possible to unreserve more products of %s than "
                        "you have in stock.\nPlease contact your system administrator "
                        "to rectify this issue.",
                        product_id.display_name,
                    )
                )
            available_reserved = sum(quants.mapped("reserved_quantity"))
            if (
                float_compare(
                    abs(quantity), available_reserved, precision_rounding=rounding
                )
                > 0
            ):
                _logger.warning(
                    "Capping unreserve of %s of %s at %s to the %s actually reserved",
                    abs(quantity),
                    product_id.display_name,
                    location_id.display_name,
                    available_reserved,
                )
                quantity = -available_reserved
                if float_is_zero(quantity, precision_rounding=rounding):
                    return []
        return super()._update_reserved_quantity(
            product_id,
            location_id,
            quantity,
            lot_id=lot_id,
            package_id=package_id,
            owner_id=owner_id,
            strict=strict,
        )
