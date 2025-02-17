# Copyright 2025 Erol Develi (https://github.com/erlinberg)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import _, api, models
from odoo.exceptions import AccessError


LOCATION_RESTRICTED_MESSAGE = _(
    "Invalid Location. You cannot process this move since you do not control the location "
    '"%s". Please contact your Adminstrator.'
)


class StockMove(models.Model):
    _inherit = "stock.move"

    @api.constrains("state", "location_id", "location_dest_id")
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
            if stock_move.state in ["draft", "waiting", "assigned", "confirmed"]:
                continue

            user_locations = self.env.user.stock_location_ids
            if stock_move.location_id not in user_locations:
                raise AccessError(
                    LOCATION_RESTRICTED_MESSAGE % stock_move.location_id.name
                )
            if stock_move.location_dest_id in user_locations:
                raise AccessError(
                    LOCATION_RESTRICTED_MESSAGE % stock_move.location_dest_id.name
                )

        return True
