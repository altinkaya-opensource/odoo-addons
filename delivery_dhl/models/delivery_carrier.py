# Copyright 2025 Erol Develi (https://github.com/erlinberg)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import base64
from datetime import datetime

import phonenumbers

from odoo import _, fields, models
from odoo.exceptions import UserError

from .dhl_request import DHLRequest

FEDEX_SERVICES = [
    ("INTERNATIONAL_ECONOMY", "International Economy"),
    ("INTERNATIONAL_FIRST", "International First"),
    ("INTERNATIONAL_PRIORITY", "International Priority"),
    ("INTERNATIONAL_PRIORITY_EXPRESS", "International Priority Express"),
]

FEDEX_PICKUP_TYPES = [
    ("CONTACT_FEDEX_TO_SCHEDULE", "Contact DHL to Schedule"),
    ("DROPOFF_AT_FEDEX_LOCATION", "Dropoff at DHL Location"),
    ("USE_SCHEDULED_PICKUP", "Use Scheduled Pickup"),
]

FEDEX_PAYMENT_TYPES = [
    ("SENDER", "Sender"),
    ("RECIPIENT", "Recipient"),
    ("THIRD_PARTY", "Third Party"),
    ("COLLECT", "Collect"),
]

FEDEX_CARRIER_CODE = [
    ("FDXE", "DHL Express"),
    ("FDXG", "DHL Ground"),
    ("FXSP", "DHL SmartPost"),
    ("FXCC", "DHL Custom Critical"),
]

FEDEX_UOM_CODES = {
    "Units": "Ea",
}


def normalize_turkish(text):
    """
    Normalize Turkish characters to their English equivalents.
    This is necessary because DHL API's labels does not support Turkish
    characters and we need to ensure that the addresses are correctly formatted.
    """
    turkish_map = {
        "ç": "c",
        "Ç": "C",
        "ğ": "g",
        "Ğ": "G",
        "ı": "i",
        "İ": "I",
        "ö": "o",
        "Ö": "O",
        "ş": "s",
        "Ş": "S",
        "ü": "u",
        "Ü": "U",
    }
    return "".join(turkish_map.get(char, char) for char in text)


class DeliveryCarrier(models.Model):
    _inherit = "delivery.carrier"
    delivery_type = fields.Selection(
        selection_add=[("dhl", "DHL")],
        ondelete={"dhl": "set default"},
    )

    # DHL uses different client IDs and secrets for different services
    # and tracking, so we need to store them separately.
    dhl_username = fields.Char()
    dhl_password = fields.Char()

    dhl_account_number = fields.Char(help="DHL Account Number")

    service_type = fields.Selection(selection=FEDEX_SERVICES)

    pickup_type = fields.Selection(selection=FEDEX_PICKUP_TYPES)
    pickup_location = fields.Char()
    pickup_close_time = fields.Char()

    # Special instructions can be added to pickup

    customs_payment_type = fields.Selection(
        selection=FEDEX_PAYMENT_TYPES,
    )

    carrier_code = fields.Selection(selection=FEDEX_CARRIER_CODE)

    stock_height = fields.Float(
        help="Height of the stock in inches for GoDEX printer",
        default=6.0,
    )

    def _get_estimated_weight_from_order_line(self, order_line):
        return order_line.product_id.weight * order_line.qty_to_deliver

    def _prepare_dhl_address(self, partner):
        """
        Prepare DHL address data from partner.
        """
        return {
            "postalCode": partner.zip or "",
            "cityName": normalize_turkish(partner.city or ""),
            "countryCode": partner.country_id.code or "TR",
            "addressLine1": normalize_turkish(partner.street or "-"),
            "addressLine2": normalize_turkish(partner.street2 or "-"),
        }

    def _prepare_dhl_contact(self, partner):
        """
        Prepare DHL contact data from partner.
        """
        return {
            "fullName": normalize_turkish(partner.name),
            "email": partner.email,
            "phone": partner.phone or partner.mobile or "",
            "companyName": normalize_turkish(partner.commercial_partner_id.name),
        }

    def _prepare_dhl_dummy_packages(self, order):
        """
        Estimate and prepare dummy packages for DHL rate
        calculation.
        """
        if order.picking_ids:
            raise UserError(_("Cannot get rates for an order with existing pickings."))

        # Create dummy pickings with order's deci
        deci = order.sale_deci * self._get_dimension_factor(order.sale_deci)
        average_pack_weight = 30
        pack_weight_threshold = 5

        # Calculate average weighted package count
        # and create them excluding the remainder
        avg_weighted_package_count = int(deci // average_pack_weight)

        # DHL requires packages to have dimensions,
        # so we create dummy packages with small dimensions
        # so it would not affect the rate calculation.
        packages = [
            {
                "weight": average_pack_weight,
                "dimensions": {
                    "length": 0.1,
                    "width": 0.1,
                    "height": 0.1,
                },
            }
            for __ in range(avg_weighted_package_count)
        ]

        # If there's a remainder weight surpassing the threshold,
        # or if there are no packages yet, we need to add it as a package
        if (
            deci % average_pack_weight > pack_weight_threshold
            or avg_weighted_package_count == 0
        ):
            packages.append(
                {
                    "weight": deci % average_pack_weight,
                    "dimensions": {
                        "length": 0.1,
                        "width": 0.1,
                        "height": 0.1,
                    },
                }
            )

        return packages

    # TODO: Prepare base customs data for DHL shipments.
    # def _prepare_dhl_base_customs_data(self, company_id, partner_id):
    #     """
    #     Prepare base customs data for DHL shipments.
    #     """
    #     return {
    #         "dutiesPayment": {
    #             "paymentType": self.customs_payment_type,
    #             "payor": {
    #                 "responsibleParty": {
    #                     "accountNumber": {
    #                         "value": str(self.dhl_account_number)
    #                         if self.customs_payment_type == "SENDER"
    #                         else str(partner_id.dhl_customer_number or "")
    #                     },
    #                     "contact": self._prepare_dhl_contact(company_id.partner_id)
    #                     if self.customs_payment_type == "SENDER"
    #                     else self._prepare_dhl_contact(partner_id),
    #                     "address": self._prepare_dhl_address(company_id.partner_id)
    #                     if self.customs_payment_type == "SENDER"
    #                     else self._prepare_dhl_address(partner_id),
    #                 }
    #             },
    #         },
    #         "commodities": [],
    #     }

    # def _prepare_dhl_commodities_entry(
    #     self, product, quantity, customs_value, customs_currency, weight
    # ):
    #     """
    #     Prepare a single commodity entry for DHL customs data.
    #     """
    #     return {
    #         "customsValue": {
    #             "currency": customs_currency,
    #             "amount": customs_value,
    #         },
    #         "unitPrice": {
    #             "currency": customs_currency,
    #             "amount": customs_value / quantity,
    #         },
    #         "description": product.categ_id.hs_code_id.with_context(
    #             lang="en_US"
    #         ).description,
    #         "name": product.with_context(lang="en_US").name,
    #         "countryOfManufacture": product.country_of_origin.code or "TR",
    #         "quantity": quantity,
    #         "harmonizedCode": product.categ_id.hs_code_id.hs_code,
    #         "quantityUnits": "Ea",
    #         "weight": {
    #             "units": "KG",
    #             "value": weight,
    #         },
    #     }

    # def _prepare_dhl_customs_data(self, picking, shipping_weight):
    #     """
    #     Prepare estimated customs data for DHL
    #     shipments on the picking and shipping weight.
    #     """
    #     data = self._prepare_dhl_base_customs_data(
    #         picking.company_id, picking.partner_id
    #     )

    #     data["commercialInvoice"] = {
    #         "purpose": picking.sale_id.dhl_shipment_purpose,
    #     }

    #     # Get non-delivery lines from the sale order
    #     lines_to_ship = picking.sale_id.order_line.filtered(
    #         lambda l: l.product_id.type in ["product", "consu"]
    #         and not l.is_delivery
    #         and not l.display_type
    #         and l.product_uom_qty > 0
    #     )

    #     # Estimate the customs value and weight
    #     # based on the order lines
    #     data["commodities"] = [
    #         self._prepare_dhl_commodities_entry(
    #             ol.product_id,
    #             ol.product_uom_qty,
    #             ol.price_subtotal,
    #             picking.sale_id.currency_id.name,
    #             shipping_weight / len(lines_to_ship),
    #         )
    #         for ol in lines_to_ship
    #     ]

    #     data["totalCustomsValue"] = {
    #         "currency": picking.sale_id.currency_id.name,
    #         "amount": sum(lines_to_ship.mapped("price_subtotal")),
    #     }

    #     return data

    def _prepare_dhl_base_rate_data(self, company_id, partner_id, delivery_date):
        """
        Prepare base rate data for DHL API requests.
        """
        return {
            "customerDetails": {
                "shipperDetails": self._prepare_dhl_address(company_id.partner_id),
                "receiverDetails": self._prepare_dhl_address(partner_id),
            },
            "accounts": [
                {
                    "typeCode": "shipper",
                    "accountNumber": {"value": str(self.dhl_account_number)},
                }
            ],
            "plannedShippingDateAndTime": delivery_date.strftime("%Y-%m-%dT%H:%M:%S"),
            "unitOfMeasurement": "metric",
            "isCustomsDeclarable": True,
        }

    def _prepare_dhl_sale_rate_data(self, order):
        """
        Prepare rate data for DHL API requests
        based on the sale order.
        """
        data = self._prepare_dhl_base_rate_data(
            order.company_id, order.partner_id, order.expected_date
        )

        # We use dummy packages because when getting rates
        # from sale.order we don't have actual packages yet.
        data["packages"] = self._prepare_dhl_dummy_packages(order)

        return data

    def _prepare_dhl_account_rate_data(self, account_move):
        """
        Prepare rate data for DHL API requests
        based on the account move (invoice).
        """
        account_move.picking_ids.ensure_one()

        data = self._prepare_dhl_base_rate_data(
            account_move.company_id,
            account_move.partner_shipping_id,
            account_move.invoice_date or fields.Date.today(),
        )

        packages = []

        for pack in account_move.picking_ids.package_ids:
            # TODO: Use Odoo's UOM conversion tools to convert all dimensions to meters
            length_m = pack.pack_length / 100.0
            width_m = pack.width / 100.0
            height_m = pack.height / 100.0
            packages.append(
                {
                    "weight": pack.shipping_weight,
                    "dimensions": {
                        "length": length_m,
                        "width": width_m,
                        "height": height_m,
                    },
                }
            )

        data["packages"] = packages

        return data

    def _prepare_dhl_shipment_data(self, picking):
        """
        Prepare shipment data for DHL API requests
        based on the stock picking.
        """
        data = {
            "accountNumber": {"value": str(self.dhl_account_number)},
            "shipAction": "CONFIRM",
            "requestedShipment": {
                "shipper": {
                    "address": self._prepare_dhl_address(picking.company_id.partner_id),
                    "contact": self._prepare_dhl_contact(picking.company_id.partner_id),
                },
                "origin": {
                    "address": self._prepare_dhl_address(picking.company_id.partner_id),
                    "contact": self._prepare_dhl_contact(picking.company_id.partner_id),
                },
                "soldTo": {
                    "address": self._prepare_dhl_address(picking.partner_id),
                    "contact": self._prepare_dhl_contact(picking.partner_id),
                },
                "recipients": [
                    {
                        "address": self._prepare_dhl_address(picking.partner_id),
                        "contact": self._prepare_dhl_contact(picking.partner_id),
                    }
                ],
                "serviceType": self.service_type,
                "preferredCurrency": picking.sale_id.currency_id.name,
                "shipDatestamp": picking.date.strftime("%Y-%m-%d"),
                "rateRequestType": ["ACCOUNT", "PREFERRED"],
                "pickupType": self.pickup_type,
                "packagingType": "YOUR_PACKAGING",
                "shippingChargesPayment": {
                    "paymentType": "SENDER" if self.payment_type else "RECIPIENT",
                    "payor": {
                        "responsibleParty": {
                            "address": self._prepare_dhl_address(picking.company_id)
                            if self.payment_type == "sender_pays"
                            else self._prepare_dhl_address(picking.partner_id),
                            "accountNumber": {
                                "value": str(self.dhl_account_number)
                                if self.payment_type == "sender_pays"
                                else str(picking.partner_id.dhl_customer_number or "")
                            },
                            "contact": self._prepare_dhl_contact(
                                picking.company_id.partner_id
                            )
                            if self.payment_type == "sender_pays"
                            else self._prepare_dhl_contact(picking.partner_id),
                        }
                    },
                },
                "customsClearanceDetail": {},
                "labelSpecification": {
                    # TODO: Make these values configurable
                    "labelFormatType": "COMMON2D",
                    "labelPrintingOrientation": "TOP_EDGE_OF_TEXT_FIRST",
                    "imageType": "ZPLII",
                    "labelOrder": "SHIPPING_LABEL_FIRST",
                    "labelRotation": "NONE",
                    "labelStockType": "STOCK_4X6",
                    "resolution": 300,
                    "customerSpecifiedDetail": {
                        "docTabContent": {
                            "docTabContentType": "MINIMUM",
                        },
                    },
                },
                "requestedPackageLineItems": [],
            },
            "labelResponseOptions": "LABEL",
        }

        packages = []
        total_weight = 0

        for pack in picking.package_ids:
            packages.append(
                {
                    "sequenceNumber": len(packages) + 1,
                    "weight": {"units": "KG", "value": pack.shipping_weight},
                    "dimensions": {
                        "length": pack.pack_length,
                        "width": pack.width,
                        "height": pack.height,
                        "units": pack.length_uom_id.name.upper(),
                    },
                }
            )
            total_weight += pack.shipping_weight
            pack.sequence = len(packages)

        data["requestedShipment"]["customsClearanceDetail"] = (
            self._prepare_dhl_customs_data(picking, total_weight)
        )
        data["requestedShipment"]["requestedPackageLineItems"] = packages

        data["requestedShipment"]["totalPackageCount"] = len(packages)

        return data

    def _prepare_dhl_zpl_godex(self, binary_zpl):
        """
        Prepare DHL API's ZPL for GoDEX printer.
        This method modifies the ZPL to fit the GoDEX printer requirements.
        """
        res = binary_zpl.decode("utf-8").replace(
            "^CF,0,0,0^PR12^MD30^PW1200^POI^CI13^LH0,20", ""
        )

        # height = real size in inches * DPI (300)
        res = res.replace("^XA", f"^XA^LL{int(self.stock_height * 300)}")

        return res.encode("utf-8")

    def dhl_rate_shipment(self, order):
        """
        Get DHL rate for the given sale order.
        """
        dhl_request = DHLRequest(
            username=self.dhl_username,
            password=self.dhl_password,
            prod=self.prod_environment,
        )
        payload = self._prepare_dhl_sale_rate_data(order)
        response = dhl_request.get_rate(payload)

        currency_name = response["exchangeRates"][0]["baseCurrency"]

        price = next(
            [
                price_data["price"]
                for price_data in response["products"][0]["totalPrice"]
                if price_data["currency"] == currency_name
            ]
        )

        # If needed, convert the price to the order's currency
        if currency_name != order.currency_id.name:
            currency = self.env["res.currency"].search(
                [("name", "=", currency_name)], limit=1
            )

            price = currency._convert(
                price,
                order.currency_id,
                order.company_id,
                fields.Date.today(),
            )

        return {
            "success": True,
            "price": price,
            "error_message": False,
            "warning_message": False,
        }

    def dhl_account_rate_shipment(self, account_move):
        """
        Get DHL rate for the given account move (invoice).
        """

        if not account_move.picking_ids:
            raise UserError(_("Cannot get rates for an invoice without pickings."))

        dhl_request = DHLRequest(
            client_id=self.dhl_client_id,
            client_secret=self.dhl_client_secret,
            prod=self.prod_environment,
        )
        payload = self._prepare_dhl_account_rate_data(account_move)
        rate_data = dhl_request.get_rates(payload)

        price = rate_data.get("price")

        # If needed, convert the price to the order's currency
        if rate_data.get("currency") != account_move.currency_id.name:
            currency = self.env["res.currency"].search(
                [("name", "=", rate_data.get("currency"))], limit=1
            )

            price = currency._convert(
                price,
                account_move.currency_id,
                account_move.company_id,
                fields.Date.today(),
            )

        return price

    def dhl_send_shipping(self, pickings):
        """
        Send DHL shipment request for the given pickings.
        """
        dhl_request = DHLRequest(
            client_id=self.dhl_client_id,
            client_secret=self.dhl_client_secret,
            prod=self.prod_environment,
        )

        result = []
        for picking in pickings:
            payload = self._prepare_dhl_shipment_data(picking)
            shipment_data = dhl_request.create_shipment(payload)["output"][
                "transactionShipments"
            ][0]

            price = shipment_data["completedShipmentDetail"]["shipmentRating"][
                "shipmentRateDetails"
            ][1]["totalNetChargeWithDutiesAndTaxes"]

            master_tracking_number = shipment_data["masterTrackingNumber"]

            picking.carrier_shipping_cost = shipment_data["completedShipmentDetail"][
                "shipmentRating"
            ]["shipmentRateDetails"][1]["totalBaseCharge"]
            picking.carrier_shipping_vat = shipment_data["completedShipmentDetail"][
                "shipmentRating"
            ]["shipmentRateDetails"][1]["totalTaxes"]
            picking.carrier_shipping_total = shipment_data["completedShipmentDetail"][
                "shipmentRating"
            ]["shipmentRateDetails"][1]["totalNetChargeWithDutiesAndTaxes"]

            picking.carrier_total_deci = shipment_data["completedShipmentDetail"][
                "shipmentRating"
            ]["shipmentRateDetails"][1]["totalBillingWeight"]["value"]

            packs_label_data = []
            for pack_label_data in shipment_data["pieceResponses"]:
                pack = picking.package_ids.filtered(
                    lambda p: p.sequence == pack_label_data["packageSequenceNumber"]
                )

                label_filename = _(
                    "dhl_label_%(seq_number)s.zpl",
                    seq_number=pack_label_data["packageSequenceNumber"],
                )
                label_binary = base64.b64encode(
                    self._prepare_dhl_zpl_godex(
                        base64.b64decode(
                            pack_label_data["packageDocuments"][0]["encodedLabel"]
                        )
                    )
                )

                packs_label_data[pack] = (label_filename, label_binary)

            picking._add_label_data(packs_label_data, self.name)

            result.append(
                {
                    "exact_price": price,
                    "tracking_number": master_tracking_number,
                }
            )

        return result

    def dhl_cancel_shipment(self, pickings):
        """
        Cancel DHL shipments for the given pickings.
        """
        dhl_request = DHLRequest(
            client_id=self.dhl_client_id,
            client_secret=self.dhl_client_secret,
            prod=self.prod_environment,
        )

        res = True
        for picking in pickings.filtered("carrier_tracking_ref"):
            payload = {
                "accountNumber": {"value": str(self.dhl_account_number)},
                "senderCountryCode": picking.company_id.partner_id.country_id.code,
                "deletionControl": "DELETE_ALL_PACKAGES",
                "trackingNumber": picking.carrier_tracking_ref,
                "carrierCode": self.carrier_code,
            }
            res = res and dhl_request.cancel_shipment(payload)["output"].get(
                "cancelledShipment", False
            )

        return res

    def dhl_tracking_state_update(self, picking):
        """Tracking state update"""
        self.ensure_one()
        if not picking.carrier_tracking_ref:
            return

        dhl_request = DHLRequest(
            client_id=self.dhl_tracking_client_id,
            client_secret=self.dhl_tracking_client_secret,
            prod=self.prod_environment,
        )

        payload = {
            "includeDetailedScans": True,
            "trackingInfo": [
                {
                    "trackingNumberInfo": {
                        "trackingNumber": picking.carrier_tracking_ref,
                    },
                }
            ],
        }

        response = dhl_request.tracking_state_update(payload)["output"][
            "completeTrackResults"
        ][0]

        picking.carrier_tracking_ref = response["trackingNumber"]
        picking.shipping_number = response["trackingNumber"]

        tracking_events = response["trackResults"][0]["scanEvents"]

        picking.tracking_state_history = "\n".join(
            [
                _(
                    "%(time)s %(date)s - [%(status_code)s] %(event)s",
                    time=datetime.fromisoformat(e.get("date", "")).strftime("%H:%M:%S")
                    if e.get("date")
                    else "",
                    date=datetime.fromisoformat(e.get("date", "")).strftime("%d/%m/%Y")
                    if e.get("date")
                    else "",
                    status_code=e.get("derivedStatusCode", ""),
                    event=e.get("eventDescription", ""),
                )
                for e in tracking_events
            ]
        )

        carrier_received_by = response["trackResults"][0]["deliveryDetails"].get(
            "receivedByName"
        )

        if carrier_received_by:
            picking.carrier_received_by = carrier_received_by

        date_delivered_iter = next(
            (
                d["dateTime"]
                for d in response["trackResults"][0]["dateAndTimes"]
                if d["type"] == "ACTUAL_DELIVERY"
            ),
            None,
        )

        date_delivered = (
            datetime.fromisoformat(date_delivered_iter).strftime("%Y-%m-%d %H:%M:%S")
            if date_delivered_iter
            else False
        )

        if date_delivered:
            picking.date_delivered = datetime.fromisoformat(date_delivered).strftime(
                "%Y-%m-%d %H:%M:%S"
            )

        return True
