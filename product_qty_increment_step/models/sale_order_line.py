# Copyright 2025 Odoo Community Association (OCA)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import _, api, models
from odoo.exceptions import ValidationError


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    @api.constrains("product_uom_qty", "product_id")
    def _check_qty_increment_step(self):
        """
        Validate that the quantity matches the product's increment step requirement.
        This constraint ensures that products with qty_increment_step > 0 can only
        be ordered in valid multiples (e.g., 250, 500, 750 if step is 250).
        """
        if self._context.get("exploding_set_contents"):
            return

        for line in self:
            # Skip validation if no product is set
            if not line.product_id:
                continue

            # Get the increment step from the product template
            step = line.product_id.product_tmpl_id.qty_increment_step

            # Skip validation if step is 0 or not set
            # (feature disabled for this product)
            if not step or step <= 0:
                continue

            # Check if quantity is a valid multiple of the step
            # Using modulo to check if there's a remainder
            if line.product_uom_qty % step != 0:
                raise ValidationError(
                    _(
                        'Product "%(product)s" must be ordered in'
                        " multiples of %(step)s.\n"
                        "Your quantity %(quantity)s is not valid.\n"
                        "Valid quantities: %(step)s, %(double)s, %(triple)s, etc."
                    )
                    % {
                        "product": line.product_id.display_name,
                        "step": int(step),
                        "quantity": int(line.product_uom_qty),
                        "double": int(step * 2),
                        "triple": int(step * 3),
                    }
                )
