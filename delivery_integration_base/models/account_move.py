import logging

from odoo import _, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = "account.move"

    delivery_ref_no = fields.Char(
        string="Delivery Reference No.",
        help="Delivery carrier reference number before"
        " the shipment is sent to the carrier.",
    )
    multiple_delivery_ref_no = fields.Text(
        string="Multiple Delivery Reference Nos.",
        help="Some carriers provide multiple reference numbers for a "
        "single shipment if it contains multiple packages.",
    )
    delivery_pickup_note = fields.Text(
        string="Pickup Note",
        help="Extra note sent to the delivery carrier when scheduling pickup.",
    )

    def send_to_shipper(self):
        """
        Action to send the shipment to the shipper.
        """
        for move in self:
            try:
                for picking in move.picking_ids.filtered(
                    lambda p: not p.carrier_tracking_ref
                ):
                    picking.with_context(send_from_account_move=True).send_to_shipper()
                    move.delivery_ref_no = picking.carrier_tracking_ref
                    move.multiple_delivery_ref_no = picking.multiple_shipping_numbers
            except UserError:
                raise
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
            lambda m: (
                m.state == "posted"
                and m.picking_ids
                and m.carrier_id
                and m.carrier_id.delivery_type not in ["fixed", "base_on_rule"]
            )
        ):
            move.send_to_shipper()
        return res

    def button_draft(self):
        """
        Override the button_draft method to cancel shipment.
        """
        res = super().button_draft()
        for move in self.filtered(
            lambda m: (
                m.picking_ids
                and m.carrier_id
                and m.carrier_id.delivery_type not in ["fixed", "base_on_rule"]
            )
        ):
            for picking in move.picking_ids:
                if picking.delivery_state != "shipping_recorded_in_carrier":
                    continue

                picking.cancel_shipment()

        return res
