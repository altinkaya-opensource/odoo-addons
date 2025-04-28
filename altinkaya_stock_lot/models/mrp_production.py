# Copyright 2025 Ismail Çağan Yılmaz (https://github.com/milleniumkid)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import _, models
from odoo.exceptions import UserError
from odoo.tools import float_is_zero


class MrpProduction(models.Model):
    _inherit = "mrp.production"

    def _prepare_stock_lot_values(self):
        res = super()._prepare_stock_lot_values()
        res.pop("name")  # Remove sequence generated name to keep our lot name logic
        return res

    def button_mark_done(self):
        """Override button_mark_done to generate lot_id automatically."""
        for line in self.move_raw_ids:
            # Ensure that products tracked by lots have a lot set
            if (
                line.product_id.tracking != "none"
                and not line.lot_ids
                and not float_is_zero(
                    line.quantity_done, precision_rounding=line.product_uom.rounding
                )
            ):
                raise UserError(
                    _("Some products are tracked by lots but no lot is set.")
                )

        # If product tracking is not 'none' and lot is not set, create a lot
        if self.product_tracking != "none" and not self.lot_producing_id:
            self.action_generate_serial()
        # Continue with the original method to complete production
        return super().button_mark_done()
