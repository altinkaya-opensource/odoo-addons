# Copyright 2022 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

# Copyright 2024 Ismail Cagan Yilmaz (https://github.com/milleniumkid)
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

import base64
from datetime import datetime

import phonenumbers
from lxml import etree
from zeep import xsd

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from .yurtici_barcode_request import YurticiBarcodeRequest
from .yurtici_request import YurticiRequest

YURTICI_OPERATION_CODES = {
    0: ("Kargo İşlem Görmemiş", "shipping_recorded_in_carrier"),
    1: ("Kargo Teslimattadır", "in_transit"),
    2: ("Kargo işlem görmüş, faturası henüz düzenlenmemiş", "in_transit"),
    3: ("Kargo Çıkışı Engellendi", "canceled_shipment"),
    4: ("Kargo daha önceden iptal edilmiştir.", "canceled_shipment"),
    5: ("Kargo Teslim edilmiştir.", "customer_delivered"),
}

YURTICI_BARCODE_OPERATION_CODES = {
    "OK": "customer_delivered",
}


class DeliveryCarrier(models.Model):
    _inherit = "delivery.carrier"

    delivery_type = fields.Selection(
        selection_add=[("yurtici", "Yurtiçi Kargo")],
        ondelete={"yurtici": "cascade"},
    )

    yurtici_username = fields.Char(string="Yurtiçi Username", help="Yurtiçi Username")
    yurtici_password = fields.Char(string="Yurtiçi Password", help="Yurtiçi Password")
    yurtici_user_lang = fields.Char(
        "UserLanguage", help="UserLanguage field for Yurtiçi"
    )

    # Extended API credentials
    yurtici_barcodeservice_username = fields.Char()
    yurtici_barcodeservice_password = fields.Char()
    yurtici_barcodeservice_customer_code = fields.Char()
    yurtici_barcodeservice_address_code = fields.Char()

    def _get_yurtici_credentials(self, service_type="basic"):
        return {
            "prod": self.prod_environment,
            "username": self.yurtici_username,
            "password": self.yurtici_password,
            "user_language": self.yurtici_user_lang,
        }

    def _get_yurtici_barcode_credentials(self):
        return {
            "prod": self.prod_environment,
            "username": self.yurtici_barcodeservice_username,
            "password": self.yurtici_barcodeservice_password,
            "user_language": self.yurtici_user_lang or "TR",
        }

    def _yurtici_address(self, partner):
        """Sender address is the address of the company, required field."""
        return partner._display_address()

    def _yurtici_phone_number(self, partner, priority="mobile"):
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
                phonenumbers.PhoneNumberFormat.E164,
            ).lstrip("+9")
        elif partner.phone or partner.mobile:
            return phonenumbers.format_number(
                phonenumbers.parse(
                    partner.phone or partner.mobile, partner.country_id.code or "TR"
                ),
                phonenumbers.PhoneNumberFormat.E164,
            ).lstrip("+9")
        else:
            raise ValidationError(
                _(
                    f"{partner.name}\nPartner's phone number is missing."
                    " It's a required field for dispatch."
                )
            )

    def _prepare_yurtici_base_vals(self, picking):
        """Prepare base values for Yurtiçi Kargo api
        :param picking record with picking to send
        :returns dict values for the connector
        """
        return {
            "cargoKey": self._get_ref_number(),
            "invoiceKey": picking.name,  # TODO: implement invoice key
            "receiverCustName": picking.partner_id.display_name,
            "receiverAddress": self._yurtici_address(picking.partner_id),
            "receiverPhone1": self._yurtici_phone_number(
                picking.partner_id, priority="mobile"
            ),
            "receiverPhone2": self._yurtici_phone_number(
                picking.partner_id, priority="phone"
            ),
            "cityName": picking.partner_id.state_id.name,
            "townName": picking.partner_id.district_id.name,
            "waybillNo": picking.name,  # TODO: implement waybill number
        }

    def _prepare_yurtici_shipping(self, picking):
        """Convert picking values for Yurtiçi Kargo api
        :param picking record with picking to send
        :returns dict values for the connector
        """
        self.ensure_one()

        if picking.carrier_package_count < 1:
            raise ValidationError(
                _("%s\nPackage count must be greater than 0.") % picking.name
            )

        if picking.picking_total_weight <= 0:
            raise ValidationError(
                _("%s\nTotal weight must be greater than 0.") % picking.name
            )

        shipment_array = []
        # We'll compose the request via some diferenced parts, like label settings,
        # address options, incoterms and so. There are lots of thing to take into
        # account to acomplish a properly formed request.
        if self.shipment_level == "send_shipment_and_barcode":
            for __ in range(picking.carrier_package_count):
                pack_vals = self._prepare_yurtici_base_vals(picking)
                pack_vals.update(
                    {
                        "desi": picking.picking_total_weight
                        / picking.carrier_package_count,
                        "kg": picking.picking_total_weight
                        / picking.carrier_package_count,
                        "cargoCount": 1,
                    }
                )
                shipment_array.append(pack_vals)
        else:
            vals = self._prepare_yurtici_base_vals(picking)
            vals.update(
                {
                    "desi": 1,
                    "kg": 1,
                    "cargoCount": picking.carrier_package_count,
                }
            )
            shipment_array.append(vals)
        return shipment_array

    def yurtici_send_shipping(self, pickings):
        """Send booking request to Yurtiçi
        :param pickings: A recordset of pickings
        :return list: A list of dictionaries although in practice it's
        called one by one and only the first item in the dict is taken. Due
        to this design, we have to inject vals in the context to be able to
        add them to the message.
        """
        if self.shipment_level == "send_shipment_and_barcode":
            return self._yk_send_shipping_with_barcode(pickings)
        else:
            return self._yk_send_shipping(pickings)

    def _prepare_yurtici_address_barcode(self, partner):
        """Prepare address values for Yurtici API"""
        return (
            f"{partner.neighbour_id.name} {partner.street} {partner.district_id.name}"
            f" {partner.state_id.name}"
        )[:100]  # Limit to 100 characters

    def _prepare_customer_info_vals(self, picking):
        """Prepare customer info values for saveCustomerWithDeliveryInfo method"""
        return {
            "shipmentInfo": {
                "deliveryUnitInfoFlag": 1,
                "estimatedDeliveryFlag": 0,
                "departureDate": datetime.now().strftime("%Y%m%d"),
                "prodId": 1,  # Default product ID
                "cargoType": 2,  # Default cargo type
            },
            "customerInfo": {
                "senderCustId": int(self.yurtici_barcodeservice_customer_code),
                "receiverCustName": picking.partner_id.display_name[:50],
                "receiverCustAddress": self._prepare_yurtici_address_barcode(
                    picking.partner_id
                ),
                "cityId": int(picking.partner_id.state_id.code),
            },
        }

    def _prepare_yurtici_barcode_shipping_vals(
        self, picking, yurtici_customer_id, yurtici_address_id
    ):
        """Prepare values for createRoutingRequestWithPayer method"""

        vals = {
            "documentData": {
                "carrierLabelingFlag": "1",  # Yurtici will create the label
                "cargoType": "2",
                "paymentType": "1" if self.payment_type == "sender_pays" else "0",
                "totalCargoCount": picking.carrier_package_count or 1,
                "totalDesi": picking.picking_total_weight,
                "totalWeight": picking.picking_total_weight,
                "personGiver": picking.company_id.name + " (DEPO)",
                "waybillNo": picking.name,
                "productCode": "STA",  # Currently only "STA" is supported
                "docCargoArray": [],
            },
            "senderCustData": {
                "kopsSenderCustId": self.yurtici_barcodeservice_customer_code,
                "kopsSenderAddressId": self.yurtici_barcodeservice_address_code,
            },
            "receiverCustData": {
                "kopsReceiverCustId": yurtici_customer_id,
                "kopsReceiverAddressId": yurtici_address_id,
            },
            "docCargoZplDataFormatVO": {
                "docCargoZplDataFormat": "TXT",
                "docCargoLabelType": "0",
                "zplType": "",
                "encoding": "",
            },
        }

        # Add cargo details
        package_count = picking.carrier_package_count or 1
        weight_per_package = picking.picking_total_weight / package_count

        for __ in range(package_count):
            cargo_data = {
                "cargoType": "2",
                "desi": weight_per_package,
                "weight": weight_per_package,
                "docCargoSpecialFieldDataArray": [
                    {
                        "specialFieldName": xsd.SkipValue,
                        "specialFieldValue": xsd.SkipValue,
                    }
                ],
            }
            vals["documentData"]["docCargoArray"].append(cargo_data)

        return vals

    def _yk_send_shipping_with_barcode(self, pickings):
        """Send shipping with barcode service integration"""
        yurtici_barcode_request = YurticiBarcodeRequest(
            **self._get_yurtici_barcode_credentials()
        )
        result = []

        for picking in pickings:
            try:
                # Save or reuse customer information if available
                partner = picking.partner_id
                if partner.yurtici_partner_id and partner.yurtici_address_id:
                    yurtici_customer_id = partner.yurtici_partner_id
                    yurtici_address_id = partner.yurtici_address_id
                else:
                    customer_vals = self._prepare_customer_info_vals(picking)
                    customer_response = yurtici_barcode_request._save_customer(
                        customer_vals
                    )

                    yurtici_customer_id = customer_response["customerInfoResult"][
                        "kopsReceiverCustId"
                    ]
                    yurtici_address_id = customer_response["customerInfoResult"][
                        "kopsReceiverAddressId"
                    ]
                    partner.yurtici_partner_id = yurtici_customer_id
                    partner.yurtici_address_id = yurtici_address_id

                # Prepare shipping values for barcode service
                shipping_vals = self._prepare_yurtici_barcode_shipping_vals(
                    picking, yurtici_customer_id, yurtici_address_id
                )
                response = yurtici_barcode_request._send_shipping(shipping_vals)

                # Extract ZPL data
                if response.docCargoV2Array:
                    for idx, cargo_data in enumerate(response.docCargoV2Array):
                        # Create an attachment for each barcode data
                        # We add ^POI to the ZPL data to print it in the
                        # correct orientation
                        # TODO: Ask Yurtiçi if they can fix this in their API
                        zpl_data = cargo_data.docCargoZpl.replace("^XA", "^XA^POI")
                        self.env["ir.attachment"].create(
                            {
                                "name": f"yurtici_barcode_{picking.name}_{idx+1}.zpl",
                                "datas": base64.b64encode(zpl_data.encode("utf-8")),
                                "res_model": picking._name,
                                "res_id": picking.id,
                                "is_delivery_document": True,
                            }
                        )

                    result.append(
                        {
                            "tracking_number": response.docId,
                            "exact_price": 0.0,
                        }
                    )

                else:
                    raise ValidationError(
                        _(
                            "Failed to create shipment: %(msg)s",
                            msg=getattr(response, "returnMessage", "Unknown error"),
                        )
                    )

            except Exception as e:
                raise ValidationError(
                    _("Error sending shipment: %(error)s", error=str(e))
                )
            finally:
                self._yurtici_log_request(yurtici_barcode_request)

        return result

    def _yk_send_shipping(self, pickings):
        """Send booking request to Yurtiçi
        :param picking: A recordset of pickings
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
            result.append({"tracking_number": response.cargoKey, "exact_price": 0.0})
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
        """Cancel the expedition based on shipment level."""
        if self.shipment_level == "send_shipment_and_barcode":
            self._yurtici_cancel_barcode_document(pickings)
        else:
            self._yurtici_cancel_standart_shipment(pickings)
        return True

    def _yurtici_cancel_standart_shipment(self, pickings):
        """Private: Cancel the expedition using standart shipment."""
        yurtici_request = YurticiRequest(**self._get_yurtici_credentials())
        for picking in pickings.filtered("carrier_tracking_ref"):
            if hasattr(self, f"{self.delivery_type}_tracking_state_update"):
                getattr(self, f"{self.delivery_type}_tracking_state_update")(picking)

            if picking.delivery_state not in [
                "shipping_recorded_in_carrier",
                "canceled_shipment",
            ]:
                raise ValidationError(
                    _(
                        """You can't cancel a shipment that
                        already has been sent to Yurtiçi"""
                    )
                )

            try:
                yurtici_request._cancel_shipment(picking.carrier_tracking_ref)
            except Exception as e:
                raise e
            finally:
                self._yurtici_log_request(yurtici_request)
        return True

    def _yurtici_cancel_barcode_document(self, pickings):
        """
        Private: Cancel the expedition for the given pickings using barcode service.
        """
        yurtici_barcode_request = YurticiBarcodeRequest(
            **self._get_yurtici_barcode_credentials()
        )

        for picking in pickings:
            if not picking.carrier_tracking_ref:
                raise ValidationError(
                    _(
                        "Picking %(picking_name)s does not have a tracking reference.",
                        picking_name=picking.name,
                    )
                )

            try:
                yurtici_barcode_request.cancel_document(
                    {
                        "docId": picking.carrier_tracking_ref,
                        "cancellationDescription": "The picking was cancelled",
                    }
                )
            except Exception as e:
                raise ValidationError(
                    _("Error while canceling shipment: %(error)s", error=str(e))
                )

        return True

    def yurtici_get_tracking_link(self, picking):
        """Provide tracking link for the customer"""
        return (
            f"https://www.yurticikargo.com/tr/online-servisler/"
            f"gonderi-sorgula?code={picking.shipping_number}"
        )

    def yurtici_tracking_state_update(self, picking):
        """Tracking state update master method based on shipment level."""
        self.ensure_one()
        if (
            self.shipment_level == "send_shipment_and_barcode"
            and picking.shipping_number
        ):
            return self.yurtici_tracking_state_update_barcode(picking)
        else:
            return self.yurtici_tracking_state_update_standart(picking)

    def yurtici_tracking_state_update_barcode(self, picking):
        """Tracking state update using barcode service"""
        self.ensure_one()

        if not picking.shipping_number:
            raise ValidationError(
                _(
                    "Picking %(picking_name)s does not have a shipping number.",
                    picking_name=picking.name,
                )
            )

        yurtici_barcode_request = YurticiBarcodeRequest(
            **self._get_yurtici_barcode_credentials()
        )

        try:
            response = yurtici_barcode_request.track_document(
                {
                    "docIdArray": [picking.shipping_number],
                    "withCargoLifecycle": "true",
                }
            )

            shipment = response["shippingDataDetailVOArray"][0]

            picking.tracking_state = shipment["cargoEventExplanation"]
            picking.delivery_state = YURTICI_BARCODE_OPERATION_CODES.get(
                shipment["cargoEventId"], picking.delivery_state
            )

            picking.carrier_total_deci = float(shipment["totalDesiKg"])
            picking.carrier_shipping_cost = float(shipment["totalPrice"])
            picking.carrier_shipping_vat = float(shipment["totalVat"])
            picking.carrier_shipping_total = float(shipment["totalAmount"])

            query = (
                f"[{shipment['cargoEventDate']}]"
                + f" [{shipment['deliveryUnitName']}]"
                + f" {shipment['cargoEventExplanation']}"
            )

            current_history = picking.tracking_state_history or ""
            if query not in current_history:
                picking.tracking_state_history = current_history + "\n" + query

            if shipment["cargoEventId"] == "OK":
                picking.date_delivered = datetime.strptime(
                    shipment["deliveryDate"], "%Y%m%d"
                )

                picking.carrier_received_by = shipment["receiverInfo"]

        except Exception as e:
            raise ValidationError(_(f"Error while updating tracking state: {str(e)}"))

        return True

    def yurtici_tracking_state_update_standart(self, picking):
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
            "shipping_number": response.shippingDeliveryItemDetailVO.docId,
        }

        if len(response.shippingDeliveryItemDetailVO.invDocCargoVOArray) > 0:
            text = ""
            for line in response.shippingDeliveryItemDetailVO.invDocCargoVOArray:
                text += f"[{line.eventDate}] [{line.unitName}] {line.eventName}\n"
            vals.update({"tracking_state_history": text})

        if response.shippingDeliveryItemDetailVO:
            vals.update(
                {
                    "carrier_total_deci": float(
                        response.shippingDeliveryItemDetailVO.totalDesiKg
                    ),
                    "carrier_shipping_cost": float(
                        response.shippingDeliveryItemDetailVO.totalPrice
                    ),
                    "carrier_shipping_vat": float(
                        response.shippingDeliveryItemDetailVO.totalVat
                    ),
                    "carrier_shipping_total": float(
                        response.shippingDeliveryItemDetailVO.totalAmount
                    ),
                }
            )

        if response.operationCode == 5:  # Delivered
            vals.update(
                {
                    "carrier_received_by": (
                        response.shippingDeliveryItemDetailVO.receiverInfo
                    ),
                    "date_delivered": datetime.strptime(
                        response.shippingDeliveryItemDetailVO.deliveryDate, "%Y%m%d"
                    ),
                }
            )

        return vals

    def yurtici_rate_shipment(self, order):
        """There's no public API so use rules for calculation."""
        return self.base_on_rule_rate_shipment(order)

    def yurtici_get_rate(self, order):
        """Get delivery price for Yurtiçi"""
        return self.base_on_rule_get_rate(order)
