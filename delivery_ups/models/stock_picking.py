# Copyright 2026 Altinkaya Enclosures, Ahmet Yigit Budak
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import _, fields, models
from odoo.exceptions import AccessError, UserError


class StockPicking(models.Model):
    _inherit = "stock.picking"

    ups_pickup_prn = fields.Char(
        string="UPS Pickup Request Number",
        help="Pickup Request Number (PRN) returned by UPS when scheduling a pickup.",
        readonly=True,
        copy=False,
    )
    ups_pickup_date = fields.Date(
        string="UPS Pickup Date",
        help="Scheduled UPS pickup date.",
        readonly=True,
        copy=False,
    )

    ups_pickup_error = fields.Text(string="UPS Pickup Error", readonly=True, copy=False)

    def action_request_ups_pickup(self):
        """Request collection without creating another shipping label."""
        self.ensure_one()
        if not self.env.user.has_group("stock.group_stock_user"):
            raise AccessError(_("Only inventory users can request a UPS pickup."))
        self.check_access_rights("write")
        self.check_access_rule("write")
        # Serialize double clicks before checking the booking or calling UPS.
        self.flush_recordset()
        self.env.cr.execute(
            "SELECT id FROM stock_picking WHERE id = %s FOR UPDATE", [self.id]
        )
        self.invalidate_recordset()
        if self.ups_pickup_prn:
            raise UserError(_("This transfer already has a UPS pickup booking."))
        if (
            self.carrier_id.delivery_type != "ups"
            or self.picking_type_code != "outgoing"
            or self.state == "cancel"
            or self.delivery_state != "shipping_recorded_in_carrier"
            or not self.shipping_number
            or self.shipping_number != self.carrier_tracking_ref
        ):
            raise UserError(
                _(
                    "Only an uncollected UPS shipment with its own label"
                    " can request pickup."
                )
            )
        if (
            not self.carrier_id.ups_pickup_type
            or self.carrier_id.ups_pickup_type == "01"
        ):
            raise UserError(
                _("Choose a non-daily UPS pickup type before requesting collection.")
            )
        success = self.carrier_id._ups_try_request_pickup(
            self,
            self.carrier_tracking_ref,
            self.carrier_total_deci,
        )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("UPS Pickup"),
                "message": _("UPS pickup booked.")
                if success
                else self.ups_pickup_error,
                "type": "success" if success else "warning",
                "sticky": not success,
                "next": {"type": "ir.actions.client", "tag": "reload"},
            },
        }

    def _ups_pickup_message(self, body):
        """Keep collection results on both the transfer and its posted invoice."""
        self.ensure_one()
        self.message_post(body=body, subtype_xmlid="mail.mt_note")
        # Warehouse users can book collection without accounting access.
        invoice = self.invoice_ids.sudo().filtered(lambda move: move.state == "posted")[
            :1
        ]
        if invoice:
            invoice.message_post(body=body, subtype_xmlid="mail.mt_note")
