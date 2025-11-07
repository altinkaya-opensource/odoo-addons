# Copyright 2025 Erol Develi (https://github.com/erlinberg)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import _, api, models
from odoo.exceptions import AccessError

LOCATION_RESTRICTED_MESSAGE = _(
    "Invalid Location. You cannot process this move since "
    "you do not control the location "
    '"%s". Please contact your Adminstrator.'
)


class StockMove(models.Model):
    _inherit = "stock.move"

    @api.constrains("procure_method", "state", "location_id", "location_dest_id")
    def check_user_location_rights(self):
        """Check if the user has the rights to process the move
        in the given locations.

        Raises:
            `AccessError`: If the user does not have the rights to process the move in
            particular location.
        """
        if not self.env.user.restrict_locations:
            return True

        for stock_move in self:
            user_warehouses = self.env.user.allowed_warehouse_ids
            if stock_move.warehouse_id not in user_warehouses:
                raise AccessError(
                    LOCATION_RESTRICTED_MESSAGE % stock_move.warehouse_id.name
                )

        return True
