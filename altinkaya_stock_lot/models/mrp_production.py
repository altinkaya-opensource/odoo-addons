# Copyright 2025 Ismail Çağan Yılmaz (https://github.com/milleniumkid)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.tools import float_is_zero


class MrpProduction(models.Model):
    _inherit = "mrp.production"

    def button_mark_done(self):
        """Override button_mark_done to generate lot_id automatically."""
        for line in self.move_raw_ids:
            # Ensure that products tracked by lots have a lot set
            if line.product_id.tracking != "none" and not line.lot_ids and not float_is_zero(
                line.quantity_done, precision_rounding=line.product_uom.rounding
            ):
                raise UserError(_("Some products are tracked by lots but no lot is set."))
            
            # If product tracking is not 'none' and lot is not set, create a lot
            if self.product_tracking != "none" and not line.lot_ids:
                # Use lot created in a different context, e.g., via the production order
                if self.lot_producing_id:
                    line.lot_ids = [(6, 0, [self.lot_producing_id.id])]
                else:
                    vals = {
                        "product_id": self.product_id.id,
                        "ref": self.origin or "",
                    }
                    # Lot creation logic should be handled via stock.lot
                    lot = self.env['stock.lot'].create(vals)
                    line.lot_ids = [(6, 0, [lot.id])]
            
        # Continue with the original method to complete production
        return super(MrpProduction, self).button_mark_done()