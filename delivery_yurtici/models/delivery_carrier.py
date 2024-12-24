# Copyright 2022 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
import phonenumbers
from odoo import _, fields, models, api
from odoo.exceptions import ValidationError
from .yurtici_request import YurticiRequest
from lxml import etree
from datetime import datetime

YURTICI_OPERATION_CODES = {
    0: ('Kargo İşlem Görmemiş', 'shipping_recorded_in_carrier'),
    1: ('Kargo Teslimattadır', 'in_transit'),
    2: ('Kargo işlem görmüş, faturası henüz düzenlenmemiş', 'in_transit'),
    3: ('Kargo Çıkışı Engellendi', 'canceled_shipment'),
    4: ('Kargo daha önceden iptal edilmiştir.', 'canceled_shipment'),
    5: ('Kargo Teslim edilmiştir.', 'customer_delivered'),
}

class DeliveryCarrier(models.Model):
    _inherit = "delivery.carrier"

    delivery_type = fields.Selection(selection_add=[("yurtici", "Yurtiçi Kargo")])

    yurtici_username = fields.Char(string="Username", help="Yurtiçi Username")
    yurtici_password = fields.Char(string="Password", help="Yurtiçi Password")
    yurtici_user_lang = fields.Char('UserLanguage', help="UserLanguage field for Yurtiçi")

    def _get_yurtici_credentials(self):
        """Access key is mandatory for every request while group and user are
        optional"""
        credentials = {
            "prod": self.prod_environment,
            "username": self.yurtici_username,
            "password": self.yurtici_password,
            'user_language': self.yurtici_user_lang,
        }
        return credentials

    def _yurtici_address(self, partner):
        """Sender address is the address of the company, required field.
        """
        return partner._display_address()

    def _yurtici_phone_number(self, partner, priority='mobile'):
        """
        Yurtici requires phone number without spaces and country code.
        We use priority selector to handle two different phone numbers.
        :param partner: recordset res.partner
        :param priority: string
        :return: phone number without spaces and country code
        """
        priority_field = getattr(partner, priority)
        if priority_field:
            return phonenumbers.format_number(
                phonenumbers.parse(priority_field, partner.country_id.code or "TR"),
                phonenumbers.PhoneNumberFormat.E164).lstrip('+9')
        elif partner.phone or partner.mobile:
            return phonenumbers.format_number(
                phonenumbers.parse(partner.phone or partner.mobile, partner.country_id.code or "TR"),
                phonenumbers.PhoneNumberFormat.E164).lstrip('+9')
        else:
            raise ValidationError(_("%s\nPartner's phone number is missing."
                                    " It's a required field for dispatch."
                                    % partner.name))

    def _prepare_yurtici_pack_info(self, picking):
        """Prepare pack info for Yurtiçi, no need to send deci and kg fields.
         They are calculated by Yurtiçi Kargo."""
        if picking.carrier_package_count < 1:
            raise ValidationError(_("%s\nPackage count must be greater than 0.") % picking.name)

        # TODO: implement stock.quant.package

        vals = {
            'desi': 1,
            'kg': 1,
            'cargoCount': picking.carrier_package_count,
        }
        return vals

    def _prepare_yurtici_shipping(self, picking):
        """Convert picking values for Yurtiçi Kargo api
        :param picking record with picking to send
        :returns dict values for the connector
        """
        self.ensure_one()
        # We'll compose the request via some diferenced parts, like label settings,
        # address options, incoterms and so. There are lots of thing to take into
        # account to acomplish a properly formed request.
        vals = {}
        vals.update(
            {
                "cargoKey": self._get_ref_number(),
                "invoiceKey": picking.name,  # TODO: implement invoice key
                "receiverCustName": picking.partner_id.display_name,
                "receiverAddress": self._yurtici_address(picking.partner_id),
                "receiverPhone1": self._yurtici_phone_number(picking.partner_id, priority='mobile'),
                "receiverPhone2": self._yurtici_phone_number(picking.partner_id, priority='phone'),
                "cityName": picking.partner_id.state_id.name,
                "townName": picking.partner_id.district_id.name,
                "waybillNo": picking.name,  # TODO: implement waybill number
            }
        )
        pack_info = self._prepare_yurtici_pack_info(picking)
        vals.update(pack_info)
        return vals

    def yurtici_send_shipping(self, pickings):
        """Send booking request to Yurtiçi
        :param pickings: A recordset of pickings
        :return list: A list of dictionaries although in practice it's
        called one by one and only the first item in the dict is taken. Due
        to this design, we have to inject vals in the context to be able to
        add them to the message.
        """
        yurtici_request = YurticiRequest(**self._get_yurtici_credentials())
        result = []
        for picking in pickings:
            vals = self._prepare_yurtici_shipping(picking)
            try:
                response = yurtici_request._send_shipping(vals)

            except Exception as e:
                raise e

            finally:
                self._yurtici_log_request(yurtici_request)

            if not response:
                result.append(vals)
                continue
            vals["tracking_number"] = response.cargoKey
            vals["exact_price"] = 0.0
            result.append(vals)
        return result

    @api.model
    def _yurtici_log_request(self, yurtici_request):
        """Helper to write raw request/response to the current picking. If debug
        is active in the carrier, those will be logged in the ir.logging as well"""
        yurtici_last_request = yurtici_last_response = False
        try:
            yurtici_last_request = etree.tostring(
                yurtici_request.history.last_sent["envelope"],
                encoding="UTF-8",
                pretty_print=True,
            )
            yurtici_last_response = etree.tostring(
                yurtici_request.history.last_received["envelope"],
                encoding="UTF-8",
                pretty_print=True,
            )
        # Don't fail hard on this. Sometimes zeep could not be able to keep history
        except Exception:
            return
        # Debug must be active in the carrier
        self.log_xml(yurtici_last_request, "yurtici_request")
        self.log_xml(yurtici_last_response, "yurtici_response")

    def yurtici_cancel_shipment(self, pickings):
        """Cancel the expedition
        :param pickings - stock.picking recordset
        :returns bool
        """
        yurtici_request = YurticiRequest(**self._get_yurtici_credentials())
        for picking in pickings.filtered("carrier_tracking_ref"):

            if hasattr(self, '%s_tracking_state_update' % self.delivery_type):  # check state before cancel
                getattr(self, '%s_tracking_state_update' % self.delivery_type)(picking)

            if picking.delivery_state not in ['shipping_recorded_in_carrier', 'canceled_shipment']:
                raise ValidationError(_("You can't cancel a shipment that already has been sent to Yurtiçi"))

            try:
                yurtici_request._cancel_shipment(picking.carrier_tracking_ref)
            except Exception as e:
                raise e
            finally:
                self._yurtici_log_request(yurtici_request)
        return True

    def yurtici_get_tracking_link(self, picking):
        """Provide tracking link for the customer"""
        return (
            f"https://www.yurticikargo.com/tr/online-servisler/"
            f"gonderi-sorgula?code={picking.shipping_number}"
        )

    def yurtici_tracking_state_update(self, picking):
        """Tracking state update"""
        self.ensure_one()
        if not picking.carrier_tracking_ref:
            return
        yurtici_request = YurticiRequest(**self._get_yurtici_credentials())

        try:
            response = yurtici_request._query_shipment(picking)
        except Exception as e:
            raise e
        finally:
            self._yurtici_log_request(yurtici_request)

        if response.errCode:
            return False

        vals = {
                "tracking_state": response.operationMessage,
                "delivery_state": YURTICI_OPERATION_CODES[response.operationCode][1],
            }

        if response.operationCode != 0 and response.shippingDeliveryItemDetailVO:
            vals.update(self._yurtici_update_picking_fields(response))

        picking.write(vals)
        return True

    def _yurtici_update_picking_fields(self, response):

        vals = {
            'shipping_number': response.shippingDeliveryItemDetailVO.docId,
        }

        if len(response.shippingDeliveryItemDetailVO.invDocCargoVOArray) > 0:
            text = ""
            for line in response.shippingDeliveryItemDetailVO.invDocCargoVOArray:
                text += "[%s] [%s] %s\n" % (line.eventDate, line.unitName, line.eventName)
            vals.update({"tracking_state_history": text})

        if response.shippingDeliveryItemDetailVO:
            vals.update({
                'carrier_total_deci': float(response.shippingDeliveryItemDetailVO.totalDesiKg),
                'carrier_shipping_cost': float(response.shippingDeliveryItemDetailVO.totalPrice),
                'carrier_shipping_vat': float(response.shippingDeliveryItemDetailVO.totalVat),
                'carrier_shipping_total': float(response.shippingDeliveryItemDetailVO.totalAmount),
            })

        if response.operationCode == 5:  # Delivered
            vals.update({'carrier_received_by': response.shippingDeliveryItemDetailVO.receiverInfo,
                         'date_delivered': datetime.strptime(response.shippingDeliveryItemDetailVO.deliveryDate,
                                                             '%Y%m%d')})

        return vals

    def yurtici_carrier_get_label(self, picking):
        """
        Yurtiçi Kargo doesn't provide label for shipments.
        They are not implemented common label on their systems.
        """
        raise NotImplementedError(
            _(
                "Yurtiçi API doesn't provide methods to print label."
            )
        )

    def yurtici_rate_shipment(self, order):
        """There's no public API so use rules for calculation."""
        return self.base_on_rule_rate_shipment(order)

    def yurtici_get_rate(self, order):
        """Get delivery price for Yurtiçi"""
        return self.base_on_rule_get_rate(order)
