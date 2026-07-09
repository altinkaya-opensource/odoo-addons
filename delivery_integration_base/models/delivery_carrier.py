# Copyright 2023 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
import logging
import math
from datetime import datetime, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_is_zero
from odoo.tools.safe_eval import safe_eval

_logger = logging.getLogger(__name__)


class DeliveryCarrier(models.Model):
    _inherit = "delivery.carrier"

    partner_id = fields.Many2one("res.partner", "Carrier")
    shipment_level = fields.Selection(
        selection=[
            ("send_shipment", "Send Shipment"),
            ("send_shipment_and_barcode", "Send Shipment and Barcode"),
        ],
        default="send_shipment",
    )
    carrier_barcode_type = fields.Selection(
        string="Barcode Type",
        selection=[
            ("pdf", "PDF"),
            ("zpl", "ZPL (Zebra)"),
        ],
        default="pdf",
        required=True,
    )
    payment_type = fields.Selection(
        selection=[("customer_pays", "Customer Pays"), ("sender_pays", "Sender Pays")],
        default="sender_pays",
        required=True,
    )
    default_printer_id = fields.Many2one("printing.printer")
    currency_id = fields.Many2one("res.currency", required=True)
    ref_sequence_id = fields.Many2one("ir.sequence", string="Reference Sequence")
    send_sms_customer = fields.Boolean(string="Send SMS to Customer", default=False)
    url_shortener_id = fields.Many2one("short.url.yourls", string="URL Shortener")
    sms_service_id = fields.Many2one("iap.account", string="SMS Service")

    barcode_text_1 = fields.Char(
        help="Some static text for this carrier to package labels.",
    )
    deci_type = fields.Selection(
        selection=[
            ("3000", "(3000)"),
            ("4000", "(4000)"),
            ("5000", "(5000)"),
            ("6000", "(6000)"),
        ],
        default="3000",
        required=True,
    )
    weight_calc_percentage = fields.Float(
        string="additional percentage for weight calculation"
    )
    # Default values for factor_a and factor_b is important.
    # Do not change them unless you want to break the logarithmic calculation.
    factor_a = fields.Float(default=2.0)
    factor_b = fields.Float(default=0.1)

    show_in_price_table = fields.Boolean(
        string="Show in Price Table",
        help="Show this carrier in Sale Order Shipment Price table",
    )
    fuel_surcharge_percentage = fields.Float(
        help="Additional Price to add after calculation of tables",
    )
    environment_fee_per_kg = fields.Float(
        string="Environment Charge per Kg",
        help="Environment fee per KG added after fuel surcharge",
    )
    postal_charge_percentage = fields.Float(
        help="For shipments below 30kg or Deci additional percentage to add",
    )
    emergency_fee_per_kg = fields.Float(
        string="Emergency Charge Per Kg",
        help="Emergency fee added after postal charge percentage",
    )

    tracking_url_prefix_no_integration = fields.Char(
        string="Tracking URL Prefix",
        help="Tracking URL prefix for carrier that has no integration.",
    )

    delivery_deadline_no_integration = fields.Integer(
        string="Delivery Deadline (In Days)",
        default=3,
        required=True,
        help="Delivery deadline for carrier that has no integration.",
    )

    dummy_pallet_threshold = fields.Float()

    dummy_pallet_weight = fields.Float()

    dummy_pallet_length = fields.Float()
    dummy_pallet_width = fields.Float()
    dummy_pallet_height = fields.Float()

    dummy_package_weight = fields.Float()

    dummy_package_length = fields.Float()
    dummy_package_width = fields.Float()
    dummy_package_height = fields.Float()

    dummy_remainder_threshold_percent = fields.Float()

    @api.constrains("factor_a", "factor_b")
    def _check_factor_values(self):
        dp = 2
        for carrier in self:
            if float_is_zero(carrier.factor_a, dp) or float_is_zero(
                carrier.factor_b, dp
            ):
                raise ValidationError(
                    _("Factor A and Factor B must be greater than 0.")
                )

    def _filter_rules_by_region(self, order):
        """
        Filter rules by defined region
        :param order: sale order
        :return: delivery.price.rule recordset
        """
        rules = self.price_rule_ids.filtered(
            lambda r: (
                order.partner_shipping_id.state_id in r.region_id.state_ids
                or order.partner_shipping_id.country_id in r.region_id.country_ids
            )
        )
        return rules

    def _get_ref_number(self):
        """
        Generate reference number based on sequence, if sequence is not defined,
        throw a ValidationError
        :return:
        """
        self.ensure_one()
        if self.ref_sequence_id:
            ref_no = self.ref_sequence_id.next_by_id()
            return ref_no
        else:
            raise ValidationError(_("No Reference Sequence defined for this carrier"))

    def _get_pickup_note_from_invoice(self, picking, max_length=None):
        invoice = picking.invoice_ids.filtered(lambda m: m.state == "posted")[:1]
        if not invoice:
            return ""
        note = " ".join((invoice.delivery_pickup_note or "").split())
        return note[:max_length] if max_length else note

    def _update_all_picking_status(self):
        """
        Update integrated pickings in a batch
        :return:
        """
        pickings = self.env["stock.picking"].search(
            [
                (
                    "carrier_id.delivery_type",
                    "not in",
                    [False, "fixed", "base_on_rule"],
                ),
                ("carrier_tracking_ref", "!=", False),
                ("date_done", ">", fields.Date.today() - timedelta(days=30)),
                (
                    "delivery_state",
                    "in",
                    ["shipping_recorded_in_carrier", "in_transit"],
                ),
            ]
        )

        for picking in pickings:
            try:
                method = f"{picking.delivery_type}_tracking_state_update"
                if hasattr(picking.carrier_id, method):
                    getattr(picking.carrier_id, method)(picking)
            except Exception as exc:
                _logger.error("Error updating picking %s state: %s", picking.name, exc)

    def _sms_notificaton_send(self, picking):
        """
        Send SMS notification to customer
        :param order: sale order
        :return:
        """
        partner_phone = picking.partner_id.mobile or picking.partner_id.phone
        if partner_phone and self.send_sms_customer and self.sms_service_id:
            sms_template = self.env.ref(
                f"delivery_{self.delivery_type}.{self.delivery_type}_sms_template"
            )
            message = sms_template._render_template(
                sms_template.body_html, sms_template.model, [picking.id]
            )[picking.id]
            composer = self.env["sms.composer"].create(
                {
                    "composition_mode": "comment",
                    "body": message,
                    "numbers": picking.partner_id.mobile,
                    "res_model": "stock.picking",
                    "res_id": picking.id,
                }
            )
            composer.action_send_sms()

        return True

    def get_tracking_link(self, picking):
        """Ask the tracking link to the service provider
        :param picking: record of stock.picking
        :return str: an URL containing the tracking link or False
        """
        res = super().get_tracking_link(picking)
        shortener = self.url_shortener_id

        if (
            not res
            and picking.carrier_id.tracking_url_prefix_no_integration
            and picking.shipping_number
        ):
            res = (
                picking.carrier_id.tracking_url_prefix_no_integration
                + picking.shipping_number
            )

        if res and shortener:
            url = shortener.shortened_urls.search(
                [("long_url", "=", res), ("id", "in", shortener.shortened_urls.ids)],
                limit=1,
            ).short_url
            if not url:
                url = shortener.shorten_url(res)
            return url
        return res

    def _get_dimension_factor(self, deci):
        """
        Calculate dimension factor based on logarithmic formula
        :param deci: deci value
        :return: dimension factor
        """
        try:
            self.ensure_one()
        except ValueError:
            return 1.0

        if deci < 0.5:
            deci = 0.5
        factor = self.factor_a - (self.factor_b * min(math.log10(deci), 2.0))
        return max(abs(factor), 1.0)

    def _get_price_available(self, order):
        self.ensure_one()
        if isinstance(order, int):
            order = self.env["sale.order"].browse(order)

        order = order.with_context(rate_carrier_id=self.id)  # Do not lose context
        order.order_line.invalidate_model()  # recompute order line deci

        deci = sum(order.order_line.mapped("deci"))
        factor = self._get_dimension_factor(deci)
        deci = deci * factor

        weight = order.sale_weight
        volume = order.sale_volume
        return self._get_price_available_price_section(order, weight, volume, deci)

    def _get_price_available_price_section(self, order, weight, volume, deci):
        dp = 4  # decimal precision
        total_delivery = sum(
            order.order_line.filtered(lambda o: o.is_delivery).mapped("price_total")
        )

        total = (order.amount_total or 0.0) - total_delivery
        total = order.currency_id._convert(
            total,
            self.currency_id,
            order.company_id,
            order.date_order or fields.Date.today(),
        )
        dummy_qty = 1.0
        price = self._get_price_from_picking(
            total, weight, volume, dummy_qty, deci, order
        )
        if not float_is_zero(self.fuel_surcharge_percentage, dp):
            price = price * (self.fuel_surcharge_percentage + 100.0) / 100.0

        if not float_is_zero(self.environment_fee_per_kg, dp):
            price = price + deci * self.environment_fee_per_kg

        if not float_is_zero(self.postal_charge_percentage, dp) and deci < 30.0:
            price = price * (self.postal_charge_percentage + 100.0) / 100.0

        if not float_is_zero(self.emergency_fee_per_kg, dp):
            price = price + deci * self.emergency_fee_per_kg

        if order.company_id.currency_id.id != self.currency_id.id:
            price = self.currency_id._convert(
                price,
                order.company_id.currency_id,
                order.company_id,
                order.date_order or fields.Date.today(),
            )
        return price

    def _get_price_from_picking(self, total, weight, volume, quantity, deci, order):
        price = 0.0
        criteria_found = False
        price_dict = {
            "price": total,
            "volume": volume,
            "weight": weight,
            "wv": volume * weight,
            "quantity": quantity,
            "deci": deci,
        }
        for line in self._filter_rules_by_region(order):
            test = safe_eval(
                line.variable + line.operator + str(line.max_value), price_dict
            )
            if test:
                price = (
                    line.list_base_price
                    + line.list_price * price_dict[line.variable_factor]
                )
                criteria_found = True
                break
        if not criteria_found:
            raise UserError(
                _(
                    "No price rule matching this order; "
                    "delivery cost cannot be computed."
                )
            )

        return price

    def _cron_update_delivery_state_no_integration(self):
        """
        Cron to update delivery state for all pickings that have no integration
        :return:
        """
        today = datetime.now()
        pickings = self.env["stock.picking"].search(
            [
                ("invoice_state", "=", "invoiced"),
                ("state", "=", "done"),
                ("date_done", "!=", False),
                ("picking_type_code", "=", "outgoing"),
                "|",
                ("delivery_state", "=", False),
                ("delivery_state", "!=", "customer_delivered"),
            ]
        )
        for picking in pickings:
            deadline = picking.date_done + timedelta(
                days=picking.carrier_id.delivery_deadline_no_integration
            )
            if today > deadline:
                picking.delivery_state = "customer_delivered"
                picking.date_delivered = fields.Datetime.now()

        return True

    def clear_delivery_data(self, picking):
        """
        Clear delivery fields for pickings
        :param picking: record of stock.picking
        :return:
        """
        picking.ensure_one()

        # Clear the barcodes
        self.env["ir.attachment"].search(
            [
                ("res_model", "=", "stock.picking"),
                ("res_id", "=", picking.id),
                ("is_delivery_document", "=", True),
            ]
        ).unlink()

        # Clear the delivery fields
        picking.carrier_tracking_ref = False
        picking.shipping_number = False
        picking.tracking_state_history = False
        picking.carrier_received_by = False
        picking.date_delivered = False
        picking.carrier_shipping_cost = False
        picking.carrier_shipping_vat = False
        picking.carrier_shipping_total = False
        picking.carrier_total_deci = False

        # Clear the invoice delivery reference
        picking.invoice_ids.write(
            {
                "delivery_ref_no": False,
            }
        )

    def cancel_shipment(self, pickings):
        res = super().cancel_shipment(pickings)
        for picking in pickings:
            if picking.delivery_state != "canceled_shipment":
                continue
            self.clear_delivery_data(picking)
        return res

    def _generate_zpl_barcode_string(self, picking, package_barcodes):
        """
        Generate ZPL barcode string for the given picking.
        """
        picking.ensure_one()

        delivery_type_label = dict(
            picking.fields_get(allfields=["delivery_type"])["delivery_type"][
                "selection"
            ]
        ).get(picking.delivery_type)

        zpl_files = []
        for idx, barcode in enumerate(package_barcodes):
            qweb_bytes = self.env["ir.actions.report"]._render_template(
                "delivery_integration_base.carrier_label",
                {
                    "docs": [picking],
                    "delivery_type_label": delivery_type_label,
                    "package_label_info": f"{idx + 1}/{len(package_barcodes)}",
                    "carrier_ref": barcode,
                },
            )

            zpl_files.append(qweb_bytes.decode("utf-8"))

        return zpl_files

    def _is_tr_business_day(self, dt):
        """Check if a date is a Turkish business day (not weekend).
        Used for same-day pickup eligibility (Mon-Fri).
        """
        d = dt.date() if isinstance(dt, datetime) else dt
        return d.weekday() < 5

    def _get_next_tr_business_day(self, dt):
        """Advance a datetime to the next business day (Mon-Fri) if needed.
        Friday is a valid pickup target, only weekends are skipped.
        """
        d = dt.date() if isinstance(dt, datetime) else dt
        while d.weekday() > 4:
            dt += timedelta(days=1)
            d = dt.date() if isinstance(dt, datetime) else dt
        return dt

    def _generate_dummy_packages(self, volumetric_weight):
        """
        Generate dummy packages for the carrier.
        This is used to create a package label without actual delivery data.
        """

        # Create dummy pickings with order's volumetric weight
        volumetric_weight = volumetric_weight * self._get_dimension_factor(
            volumetric_weight
        )

        is_pallet = volumetric_weight >= self.dummy_pallet_threshold
        if is_pallet:
            pack_weight = self.dummy_pallet_weight or 100.0
            dimensions = {
                "length": self.dummy_pallet_length or 120.0,
                "width": self.dummy_pallet_width or 80.0,
                "height": self.dummy_pallet_height or 120.0,
            }
        else:
            pack_weight = self.dummy_package_weight or 30.0
            dimensions = {
                "length": self.dummy_package_length or 30.0,
                "width": self.dummy_package_width or 30.0,
                "height": self.dummy_package_height or 30.0,
            }

        packages = []

        while volumetric_weight > pack_weight:
            packages.append(
                {
                    "weight": pack_weight,
                    "dimensions": dimensions,
                    "is_pallet": is_pallet,
                }
            )

            volumetric_weight -= pack_weight

        if (
            not packages
            or volumetric_weight > self.dummy_remainder_threshold_percent * pack_weight
        ):
            packages.append(
                {
                    "weight": volumetric_weight,
                    "dimensions": dimensions,
                    "is_pallet": is_pallet,
                }
            )

        return packages
