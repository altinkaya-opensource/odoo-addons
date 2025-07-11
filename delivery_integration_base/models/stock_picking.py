# # Copyright 2023 Yiğit Budak (https://github.com/yibudak)
# # License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo import _, fields, models
from odoo.exceptions import ValidationError


class StockPicking(models.Model):
    _inherit = "stock.picking"

    carrier_package_count = fields.Integer(
        "Package Count", help="Number of packages", default=1
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
        """ Only send the picking to the shipper if the send
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
        if (
            self.carrier_id.delivery_type not in [False, "base_on_rule", "fixed"]
            and self.carrier_id.send_sms_customer
            and self.carrier_id.sms_service_id
        ):
            self.carrier_id.with_delay()._sms_notificaton_send(self)
        return True

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
            method = f"{picking.delivery_type}_carrier_get_label"
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
        label_name = (
            f"{self.carrier_id.delivery_type}_etiket_"
            f"{self.carrier_tracking_ref}.{self.carrier_id.carrier_barcode_type}"
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
        report_name = "delivery_integration_base.carrier_label"
        delivery_type_label = dict(
            self.fields_get(allfields=["delivery_type"])["delivery_type"]["selection"]
        ).get(self.delivery_type)
        package_count = self.carrier_package_count or 1
        for i in range(package_count):
            current_label = f"{i+1}/{package_count}"
            qweb_bytes = self.env["ir.actions.report"]._render_template(
                report_name,
                {
                    "docs": [self],
                    "zpl_raw": data,
                    "delivery_type_label": delivery_type_label,
                    "package_label_info": current_label,
                },
            )
            qweb_text = qweb_bytes.decode("utf-8")
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
            self.with_delay().message_post_with_template(mail_template.id)
            self.write(
                {
                    "mail_sent": True,
                }
            )
        return True

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
