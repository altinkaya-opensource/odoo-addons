# # Copyright 2023 Yiğit Budak (https://github.com/yibudak)
# # License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
import base64

from odoo import _, fields, models

from odoo.addons.queue_job.exception import RetryableJobError
from odoo.addons.queue_job.job import identity_exact


class StockPicking(models.Model):
    _inherit = "stock.picking"

    carrier_package_count = fields.Integer(
        "Package Count", help="Number of packages", default=0
    )
    carrier_total_deci = fields.Float(help="Carrier total reception Deci")
    picking_total_deci = fields.Float(
        compute="_compute_picking_total_deci",
        help="Dynamic Total Deci, calculated based on the move lines.",
    )
    picking_total_weight = fields.Float(
        help="Shipments Total Measured Exit Deci weight"
    )
    carrier_received_by = fields.Char("Received By", help="Received by")
    shipping_number = fields.Char(help="Shipping Tracking Number")
    multiple_shipping_numbers = fields.Text(
        help="Some carriers provide multiple tracking numbers for a "
        "single shipment if it contains multiple packages."
    )
    mail_sent = fields.Boolean("Mail Sent To Customer", default=False, copy=False)
    delivery_payment_type = fields.Selection(
        related="carrier_id.payment_type", readonly=True
    )

    # Accounting fields
    sale_shipping_cost = fields.Monetary(
        help="Sale shipping cost no VAT",
        compute="_compute_sale_shipping_cost",
        currency_field="shipping_currency_id",
    )
    sale_shipping_cost_try = fields.Monetary(
        "Sale Shipping Cost TRY",
        help="Sale shipping cost no VAT",
        compute="_compute_sale_shipping_cost",
        currency_field="currency_id_try",
    )
    carrier_shipping_cost = fields.Monetary(
        help="Carrier shipping cost",
        default=0.0,
        currency_field="shipping_currency_id",
    )
    carrier_shipping_cost_try = fields.Monetary(
        "Shipping Cost (TRY)",
        help="Shipping Cost No VAT (TRY)",
        currency_field="currency_id_try",
        compute="_compute_shipping_cost_try",
    )
    carrier_shipping_vat = fields.Monetary(
        "Shipping VAT",
        help="Shipping VAT",
        default=0.0,
        currency_field="shipping_currency_id",
    )
    carrier_shipping_total = fields.Monetary(
        "Shipping Total",
        help="Shipping total",
        default=0.0,
        currency_field="shipping_currency_id",
    )
    shipping_currency_id = fields.Many2one(
        "res.currency",
        "Carrier Currency",
        help="Carrier Currency",
        compute="_compute_shipping_currency_id",
    )
    currency_id_try = fields.Many2one(
        "res.currency",
        "Currency",
        related="company_id.currency_id",
        readonly=True,
    )

    def send_to_shipper(self):
        """Only send the picking to the shipper if the send
        request is from the account move.
        """
        if not self._context.get("send_from_account_move", False):
            return False
        return super().send_to_shipper()

    def _compute_shipping_cost_try(self):
        for picking in self:
            try_currency = picking.shipping_currency_id._convert(
                picking.carrier_shipping_cost,
                picking.currency_id_try,
                picking.company_id,
                picking.date,
            )
            picking.carrier_shipping_cost_try = try_currency

    def _compute_shipping_currency_id(self):
        """
        Compute the shipping currency based on the priorities
        :return:
        """
        for picking in self:
            picking.shipping_currency_id = (
                picking.carrier_id.currency_id or picking.company_id.currency_id
            )

    def _compute_picking_total_deci(self):
        """
        Compute the picking total deci based on the move lines
        :return:
        """
        for picking in self:
            deci = sum(picking.mapped("move_ids.sale_line_id.last_deci"))
            factor = picking.carrier_id._get_dimension_factor(deci)
            picking.picking_total_deci = deci * factor

    def _compute_sale_shipping_cost(self):
        """
        Compute the shipping cost based on active move lines
        :return:
        """
        for picking in self:
            total_cost = 0.0

            # always assign a value
            picking.sale_shipping_cost = total_cost
            picking.sale_shipping_cost_try = total_cost

            sale_move_lines = picking.move_ids.filtered("sale_line_id")
            for move in sale_move_lines:
                ol = move.sale_line_id
                sale_id = ol.order_id
                sale_deci = sum(sale_id.mapped("order_line.last_deci"))
                ol_deci = ol.last_deci
                deliver_cost = sum(
                    sale_id.order_line.filtered("is_delivery").mapped("price_unit")
                )

                if deliver_cost and sale_deci:
                    # compute weighted average
                    total_cost += (deliver_cost / sale_deci) * ol_deci
                picking.sale_shipping_cost = total_cost
                try_currency = sale_id.currency_id._convert(
                    total_cost,
                    picking.currency_id_try,
                    picking.company_id,
                    picking.date,
                )
                picking.sale_shipping_cost_try = try_currency

    def _tracking_status_notification(self):
        """Queue shipment notices after the carrier status has been saved."""
        for picking in self:
            if (
                picking.carrier_id.delivery_type not in [False, "base_on_rule", "fixed"]
                and picking.carrier_id.send_sms_customer
                and picking.carrier_id.sms_service_id
            ):
                picking.carrier_id.with_delay()._sms_notificaton_send(picking)
        self.button_mail_send()
        return True

    def write(self, vals):
        """Notify once on departure, or when a missing tracking number arrives."""
        entering_transit = self.browse()
        awaiting_tracking = self.browse()
        if vals.get("delivery_state") == "in_transit":
            entering_transit = self.filtered(lambda p: p.delivery_state != "in_transit")
        if vals.get("shipping_number"):
            awaiting_tracking = self.filtered(lambda p: not p.shipping_number)

        result = super().write(vals)
        entering_transit._tracking_status_notification()
        (awaiting_tracking - entering_transit).filtered(
            lambda p: p.delivery_state == "in_transit"
        ).button_mail_send()
        return result

    def action_print_delivery_documents(self):
        """
        Print the delivery documents for the picking.
        """
        for picking in self.filtered("carrier_id"):
            delivery_documents = self.env["ir.attachment"].search(
                [
                    ("res_model", "=", "stock.picking"),
                    ("res_id", "=", picking.id),
                    ("is_delivery_document", "=", True),
                ]
            )

            if delivery_documents:
                for doc in delivery_documents:
                    self.carrier_id.default_printer_id.print_document(
                        report=None,
                        content=base64.b64decode(doc.datas),
                    )

    def _get_delivery_mail_partner(self):
        """Return the partner that should receive delivery tracking emails."""
        self.ensure_one()
        if self.partner_id.email:
            return self.partner_id
        if self.sale_id.partner_id.email:
            return self.sale_id.partner_id
        return self.env["res.partner"]

    def button_mail_send(self):
        """Queue one customer shipment email, shared by automatic and manual sends."""
        for picking in self:
            if picking._can_send_delivery_mail():
                picking.with_delay(identity_key=identity_exact)._send_delivery_mail()
        return True

    def _send_delivery_mail(self):
        """Send in the queue worker and mark success only after provider acceptance."""
        self.ensure_one()
        # Pending-job identity deduplication does not cover an already running
        # job. Serialize manual/automatic jobs for this picking before sending.
        self.flush_recordset(["mail_sent"])
        self.env.cr.execute(
            "SELECT id FROM stock_picking WHERE id = %s FOR UPDATE", (self.id,)
        )
        self.invalidate_recordset()
        if not self._can_send_delivery_mail():
            return False

        template = self.env.ref("delivery_integration_base.delivery_mail_template")
        mail_id = template.send_mail(
            self.id,
            email_values={
                # Inspect the result before cleanup. Keep the message on the
                # picking even when the outgoing mail is subsequently deleted.
                "auto_delete": False,
                "is_notification": True,
            },
        )
        mail = self.env["mail.mail"].sudo().browse(mail_id)
        mail.send()
        # Some connectors, including Postmark, record failures without raising.
        if mail.state != "sent":
            raise RetryableJobError(
                _("Shipment email was not sent: %s", mail.failure_reason or mail.state)
            )
        self.mail_sent = True
        if template.auto_delete:
            mail.unlink()
        return True

    def _can_send_delivery_mail(self):
        """Only notify customers about numbered, non-cancelled outgoing shipments."""
        self.ensure_one()
        return bool(
            not self.mail_sent
            and self.shipping_number
            and self.state != "cancel"
            and self.delivery_state != "canceled_shipment"
            and self.picking_type_code == "outgoing"
            and self.location_dest_id.usage == "customer"
            and self._get_delivery_mail_partner()
        )

    def _add_delivery_cost_to_so(self):
        """
        # Todo: compute delivery cost and add it to the sale order,
        # odoo's function doesn't meet the requirements.
        :return:
        """
        self.ensure_one()
        return True
        # sale_order = self.sale_id
        # if sale_order.invoice_shipping_on_delivery:
        #     carrier_price = self.carrier_price * (1.0 + (float(self.carrier_id.margin) / 100.0)) # noqa
        #     sale_order._create_delivery_line(self.carrier_id, carrier_price)

    def open_record(self):
        form_id = self.env.ref("stock.view_picking_form")
        return {
            "type": "ir.actions.act_window",
            "res_model": "stock.picking",
            "res_id": self.id,
            "view_type": "form",
            "view_mode": "form",
            "view_id": form_id.id,
            "context": {},
            "target": "current",
        }
