import logging

from odoo import _, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = "account.move"

    def send_to_shipper(self):
        """
        Action to send the shipment to the shipper.
        """
        for move in self:
            try:
                for picking in move.picking_ids:
                    picking.with_context(send_from_account_move=True).send_to_shipper()
                    picking.shipping_number = picking.carrier_tracking_ref
                    move.delivery_ref_no = picking.carrier_tracking_ref
            except Exception as e:
                _logger.error(
                    "Error sending shipment from invoice for move %s: %s",
                    move.id,
                    e,
                    exc_info=True,
                )
                raise UserError(_("Error sending shipment from invoice: %s", e)) from e

        return True

    def action_post(self):
        """
        Override the action_post method to ensure shipments are sent.
        """
        res = super().action_post()
        for move in self.filtered(
            lambda m: m.state == "posted"
            and m.picking_ids
            and m.carrier_id
            and m.carrier_id.delivery_type not in ["fixed", "base_on_rule"]
        ):
            move.send_to_shipper()
        return res

    def button_draft(self):
        """
        Override the button_draft method to cancel shipment.
        """
        res = super().button_draft()
        for move in self.filtered(
            lambda m: m.picking_ids
            and m.carrier_id
            and m.carrier_id.delivery_type not in ["fixed", "base_on_rule"]
        ):
            for picking in move.picking_ids:
                if picking.delivery_state != "shipping_recorded_in_carrier":
                    continue

                picking.cancel_shipment()

        return res
