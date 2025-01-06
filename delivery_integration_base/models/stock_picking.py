# Copyright 2023 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

# Copyright 2024 Ismail Çağan Yılmaz (https://github.com/milleniumkid)
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

from odoo import models, _, fields, api
from odoo.exceptions import ValidationError


class StockPicking(models.Model):
    _inherit = "stock.picking"

    carrier_package_count = fields.Integer(
        "Package Count", help="Number of packages", default=1
    )
    carrier_total_weight = fields.Float(
        "Carrier Total Weight", help="Decimal of packages"
    )
    delivery_state = fields.Selection(
        selection=[
            ("shipping_recorded_in_carrier", "Shipping recorded in carrier"),
            ("in_transit", "In transit"),
            ("canceled_shipment", "Canceled shipment"),
            ("incident", "Incident"),
            ("customer_delivered", "Customer delivered"),
            ("warehouse_delivered", "Warehouse delivered"),
            ("no_update", "No more updates from carrier"),
        ],
        ondelete={
            "shipping_recorded_in_carrier": "set default",
            "in_transit": "set default",
            "canceled_shipment": "set default",
            "incident": "set default",
            "customer_delivered": "set default",
            "warehouse_delivered": "set default",
            "no_update": "set default"
            },
        string="Delivery Status",
        default="draft",
        copy=False,
        tracking=True,
    )
    picking_total_weight = fields.Float(
        "Picking Total Weight", help="Decimal of packages"
    )
    carrier_received_by = fields.Char("Received By", help="Received by")
    shipping_number = fields.Char("Shipping Number", help="Shipping Tracking Number")
    mail_sent = fields.Boolean("Mail Sent To Customer", default=False, copy=False)

    # Accounting fields
    carrier_shipping_cost = fields.Monetary(
        "Shipping Cost",
        help="Shipping cost",
        default=0.0,
        currency_field="carrier_currency_id",
    )
    carrier_shipping_vat = fields.Monetary(
        "Shipping VAT",
        help="Shipping VAT",
        default=0.0,
        currency_field="carrier_currency_id",
    )
    carrier_shipping_total = fields.Monetary(
        "Shipping Total",
        help="Shipping total",
        default=0.0,
        currency_field="carrier_currency_id",
    )
    carrier_currency_id = fields.Many2one(
        "res.currency",
        "Carrier Currency",
        help="Carrier Currency",
        related="carrier_id.currency_id",
        readonly=True,
    )

    def _tracking_status_notification(self):
        if (
            self.carrier_id.delivery_type not in [False, "base_on_rule", "fixed"]
            and self.carrier_id.send_sms_customer
            and self.carrier_id.sms_service_id
        ):
            self.carrier_id.with_delay()._sms_notificaton_send(self)

    @api.onchange("delivery_state")
    def _onchange_delivery_state(self):
        if self.delivery_state not in dict(self._fields["delivery_state"].selection):
            raise ValidationError(_("Invalid delivery state: %s") % self.delivery_state)

    def write(self, vals):
        if "delivery_state" in vals:
            if (
                vals["delivery_state"] == "in_transit"
                and vals["delivery_state"] != self.delivery_state
            ):
                self._tracking_status_notification()
        return super().write(vals)

    def carrier_get_label(self):
        """Call to the service provider API which should have the method
        defined in the model as:
            <my_provider>_carrier_get_label
        It can be triggered manually or by the cron."""
        for picking in self.filtered("carrier_id"):
            method = "%s_carrier_get_label" % picking.delivery_type
            carrier = picking.carrier_id
            if hasattr(carrier, method) and carrier.default_printer_id:
                data = getattr(carrier, method)(picking)
                if carrier.attach_barcode:
                    self._attach_barcode(data)
                else:
                    self._print_barcode(data)
            else:
                raise ValidationError(
                    _("No default printer defined for the carrier %s") % carrier.name
                )

    def _attach_barcode(self, data):
        """
        Attach the barcode to the picking as PDF
        :param data:
        :return: boolean
        """
        label_name = "{}_etiket_{}.{}".format(
            self.carrier_id.delivery_type,
            self.carrier_tracking_ref,
            self.carrier_id.carrier_barcode_type,
        )
        self.message_post(
            body=(_("%s etiket") % self.carrier_id.display_name),
            attachments=[(label_name, data)],
        )
        return True

    def _print_barcode(self, data):
        """
        Print the barcode on the picking as ZPL format.
        It uses the carrier's qweb template.
        :param data:
        :return: boolean
        """
        carrier = self.carrier_id
        printer = carrier.default_printer_id
        report_name = "delivery_{0}.{0}_carrier_label".format(carrier.delivery_type)
        qweb_text = self.env.ref(report_name).render_qweb_text(
            [carrier.id], data={"zpl_raw": data}
        )[0]
        printer.print_document(report_name, qweb_text, doc_form="txt")
        return True

    def button_mail_send(self):
        """
        Send the shipment status by email
        :return: boolean
        """
        mail_template = self.env.ref("delivery_integration_base.delivery_mail_template")
        email = self.partner_id.email or self.sale_id.partner_id.email
        if email and not self.mail_sent:
            mail_template.with_delay().send_mail(
                res_id=self.id,
                force_send=True,
                raise_exception=False,
                email_values={"email_to": self.partner_id.email},
            )
            self.write(
                {
                    "mail_sent": True,
                }
            )

        return True
