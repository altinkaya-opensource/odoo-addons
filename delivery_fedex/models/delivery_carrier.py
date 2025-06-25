# Copyright 2025 Erol Develi (https://github.com/erlinberg)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import base64
from datetime import datetime

import phonenumbers

from odoo import _, fields, models
from odoo.exceptions import UserError

from .fedex_request import FedExRequest

FEDEX_SERVICES = [
    ("INTERNATIONAL_ECONOMY", "International Economy"),
    ("INTERNATIONAL_FIRST", "International First"),
    ("INTERNATIONAL_PRIORITY", "International Priority"),
    ("INTERNATIONAL_PRIORITY_EXPRESS", "International Priority Express"),
]

FEDEX_PICKUP_TYPES = [
    ("CONTACT_FEDEX_TO_SCHEDULE", "Contact FedEx to Schedule"),
    ("DROPOFF_AT_FEDEX_LOCATION", "Dropoff at FedEx Location"),
    ("USE_SCHEDULED_PICKUP", "Use Scheduled Pickup"),
]

FEDEX_PAYMENT_TYPES = [
    ("SENDER", "Sender"),
    ("RECIPIENT", "Recipient"),
    ("THIRD_PARTY", "Third Party"),
    ("COLLECT", "Collect"),
]

FEDEX_CARRIER_CODE = [
    ("FDXE", "FedEx Express"),
    ("FDXG", "FedEx Ground"),
    ("FXSP", "FedEx SmartPost"),
    ("FXCC", "FedEx Custom Critical"),
]

FEDEX_UOM_CODES = {
    "Units": "Ea",
}


# Normalize Turkish characters to their English equivalents
# This is necessary because FedEx API does not support Turkish characters
# and we need to ensure that the addresses are correctly formatted.
def normalize_turkish(text):
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
        selection_add=[("fedex", "FedEx")],
        ondelete={"fedex": "set default"},
    )
    fedex_client_id = fields.Char(string="Client ID", help="FedEx Client ID")
    fedex_client_secret = fields.Char(help="FedEx Client Secret")
    fedex_account_number = fields.Integer(help="FedEx Account Number")

    service_type = fields.Selection(selection=FEDEX_SERVICES)
    pickup_type = fields.Selection(selection=FEDEX_PICKUP_TYPES)
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

    def _prepare_fedex_address(self, partner):
        """
        Prepare FedEx address data from partner.
        """
        return {
            "streetLines": [
                normalize_turkish(partner.street or ""),
                normalize_turkish(partner.street2 or ""),
            ],
            "city": normalize_turkish(partner.city),
            "postalCode": partner.zip,
            "countryCode": partner.country_id.code,
            "residential": False,
        }

    def _prepare_fedex_contact(self, partner):
        """
        Prepare FedEx contact data from partner.
        """
        contact = {
            "personName": normalize_turkish(partner.name + "çışüğİÜÇĞŞ"),
            "emailAddress": partner.email,
            "companyName": normalize_turkish(partner.commercial_partner_id.name),
        }

        if partner.phone or partner.mobile:
            # Use phonenumbers library to format the phone number
            # because FedEx API requires raw format
            raw_number = phonenumbers.format_number(
                phonenumbers.parse(
                    partner.phone or partner.mobile, partner.country_id.code
                ),
                phonenumbers.PhoneNumberFormat.E164,
            )

            # FedEx API requires the number and extension to be separated
            contact["phoneNumber"] = raw_number[len(raw_number) - 10 :]
            contact["phoneExtension"] = raw_number[: len(raw_number) - 10]

        return contact

    def _prepare_fedex_dummy_packages(self, order):
        """
        Estimate and prepare dummy packages for FedEx rate
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

        packages = [
            {
                "weight": {"units": "KG", "value": average_pack_weight},
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
                    "weight": {"units": "KG", "value": deci % average_pack_weight},
                }
            )

        return packages

    def _prepare_fedex_base_customs_data(self, company_id, partner_id):
        """
        Prepare base customs data for FedEx shipments.
        """
        return {
            "dutiesPayment": {
                "paymentType": self.customs_payment_type,
                "payor": {
                    "responsibleParty": {
                        "accountNumber": {
                            "value": str(self.fedex_account_number)
                            if self.customs_payment_type == "SENDER"
                            else str(partner_id.fedex_customer_number or "")
                        },
                        "contact": self._prepare_fedex_contact(company_id.partner_id)
                        if self.customs_payment_type == "SENDER"
                        else self._prepare_fedex_contact(partner_id),
                        "address": self._prepare_fedex_address(company_id.partner_id)
                        if self.customs_payment_type == "SENDER"
                        else self._prepare_fedex_address(partner_id),
                    }
                },
            },
            "commodities": [],
        }

    def _prepare_fedex_commodities_entry(
        self, product, quantity, customs_value, customs_currency, weight
    ):
        """
        Prepare a single commodity entry for FedEx customs data.
        """
        return {
            "customsValue": {
                "currency": customs_currency,
                "amount": customs_value,
            },
            "unitPrice": {
                "currency": customs_currency,
                "amount": customs_value / quantity,
            },
            "description": product.categ_id.hs_code_id.with_context(
                lang="en_US"
            ).description,
            "name": product.with_context(lang="en_US").name,
            "countryOfManufacture": product.country_of_origin.code or "TR",
            "quantity": quantity,
            "harmonizedCode": product.categ_id.hs_code_id.hs_code,
            "quantityUnits": "Ea",
            "weight": {
                "units": "KG",
                "value": weight,
            },
        }

    def _prepare_fedex_customs_data(self, picking, shipping_weight):
        """
        Prepare estimated customs data for FedEx
        shipments on the picking and shipping weight.
        """
        data = self._prepare_fedex_base_customs_data(
            picking.company_id, picking.partner_id
        )

        data["commercialInvoice"] = {
            "purpose": picking.sale_id.fedex_shipment_purpose,
        }

        # Get non-delivery lines from the sale order
        lines_to_ship = picking.sale_id.order_line.filtered(
            lambda l: l.product_id.type in ["product", "consu"]
            and not l.is_delivery
            and not l.display_type
            and l.product_uom_qty > 0
        )

        # Estimate the customs value and weight
        # based on the order lines
        data["commodities"] = [
            self._prepare_fedex_commodities_entry(
                ol.product_id,
                ol.product_uom_qty,
                ol.price_subtotal,
                picking.sale_id.currency_id.name,
                shipping_weight / len(lines_to_ship),
            )
            for ol in lines_to_ship
        ]

        data["totalCustomsValue"] = {
            "currency": picking.sale_id.currency_id.name,
            "amount": sum(lines_to_ship.mapped("price_subtotal")),
        }

        return data

    def _prepare_fedex_base_rate_data(self, company_id, partner_id, delivery_date):
        """
        Prepare base rate data for FedEx API requests.
        """
        return {
            "accountNumber": {"value": str(self.fedex_account_number)},
            "requestedShipment": {
                "shipper": {
                    "address": self._prepare_fedex_address(company_id.partner_id)
                },
                "recipient": {"address": self._prepare_fedex_address(partner_id)},
                "serviceType": self.service_type,
                "preferredCurrency": self.currency_id.name,
                "rateRequestType": ["PREFERRED"],
                "pickupType": self.pickup_type,
                "packagingType": "YOUR_PACKAGING",
                "shipDateStamp": delivery_date.strftime("%Y-%m-%d"),
                "requestedPackageLineItems": [],
            },
            "carrierCodes": [self.carrier_code],
        }

    def _prepare_fedex_sale_rate_data(self, order):
        """
        Prepare rate data for FedEx API requests
        based on the sale order.
        """
        data = self._prepare_fedex_base_rate_data(
            order.company_id, order.partner_id, order.expected_date
        )

        # We use dummy packages because when getting rates
        # from sale.order we don't have actual packages yet.
        data["requestedShipment"]["requestedPackageLineItems"] = (
            self._prepare_fedex_dummy_packages(order)
        )

        return data

    def _prepare_fedex_account_rate_data(self, account_move):
        """
        Prepare rate data for FedEx API requests
        based on the account move (invoice).
        """
        account_move.picking_ids.ensure_one()

        data = self._prepare_fedex_base_rate_data(
            account_move.company_id,
            account_move.partner_shipping_id,
            account_move.invoice_date or fields.Date.today(),
        )

        packages = []
        total_weight = 0

        for pack in account_move.picking_ids.package_ids:
            packages.append(
                {
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

        data["requestedShipment"]["customsClearanceDetail"] = (
            self._prepare_fedex_customs_data(account_move.picking_ids, total_weight)
        )
        data["requestedShipment"]["requestedPackageLineItems"] = packages

        data["requestedShipment"]["totalPackageCount"] = len(packages)

        return data

    def _prepare_fedex_shipment_data(self, picking):
        """
        Prepare shipment data for FedEx API requests
        based on the stock picking.
        """
        data = {
            "accountNumber": {"value": str(self.fedex_account_number)},
            "shipAction": "CONFIRM",
            "requestedShipment": {
                "shipper": {
                    "address": self._prepare_fedex_address(
                        picking.company_id.partner_id
                    ),
                    "contact": self._prepare_fedex_contact(
                        picking.company_id.partner_id
                    ),
                },
                "origin": {
                    "address": self._prepare_fedex_address(
                        picking.company_id.partner_id
                    ),
                    "contact": self._prepare_fedex_contact(
                        picking.company_id.partner_id
                    ),
                },
                "soldTo": {
                    # TODO: Set the correct partner (shipping partner)
                    "address": self._prepare_fedex_address(picking.partner_id),
                    "contact": self._prepare_fedex_contact(picking.partner_id),
                },
                "recipients": [
                    # TODO: Set the correct partner (shipping partner)
                    {
                        "address": self._prepare_fedex_address(picking.partner_id),
                        "contact": self._prepare_fedex_contact(picking.partner_id),
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
                            "address": self._prepare_fedex_address(picking.company_id)
                            if self.payment_type == "sender_pays"
                            else self._prepare_fedex_address(picking.partner_id),
                            "accountNumber": {
                                "value": str(self.fedex_account_number)
                                if self.payment_type == "sender_pays"
                                else str(picking.partner_id.fedex_customer_number or "")
                            },
                            "contact": self._prepare_fedex_contact(
                                picking.company_id.partner_id
                            )
                            if self.payment_type == "sender_pays"
                            else self._prepare_fedex_contact(picking.partner_id),
                        }
                    },
                },
                "customsClearanceDetail": {},
                "labelSpecification": {
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
            self._prepare_fedex_customs_data(picking, total_weight)
        )
        data["requestedShipment"]["requestedPackageLineItems"] = packages

        data["requestedShipment"]["totalPackageCount"] = len(packages)

        return data

    def _prepare_fedex_zpl_godex(self, binary_zpl):
        res = binary_zpl.decode("utf-8").replace(
            "^CF,0,0,0^PR12^MD30^PW1200^POI^CI13^LH0,20", ""
        )

        # height = real size in inches * DPI (300)
        res = res.replace("^XA", f"^XA^LL{int(self.stock_height * 300)}")

        return res.encode("utf-8")

    def fedex_rate_shipment(self, order):
        """
        Get FedEx rate for the given sale order.
        """
        fedex_request = FedExRequest(
            client_id=self.fedex_client_id,
            client_secret=self.fedex_client_secret,
            prod=self.prod_environment,
        )
        payload = self._prepare_fedex_sale_rate_data(order)
        rate_data = fedex_request.get_rates(payload)

        price = rate_data.get("price")

        # If needed, convert the price to the order's currency
        if rate_data.get("currency") != order.currency_id.name:
            currency = self.env["res.currency"].search(
                [("name", "=", rate_data.get("currency"))], limit=1
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

    def fedex_account_rate_shipment(self, account_move):
        """
        Get FedEx rate for the given account move (invoice).
        """

        if not account_move.picking_ids:
            raise UserError(_("Cannot get rates for an invoice without pickings."))

        fedex_request = FedExRequest(
            client_id=self.fedex_client_id,
            client_secret=self.fedex_client_secret,
            prod=self.prod_environment,
        )
        payload = self._prepare_fedex_account_rate_data(account_move)
        rate_data = fedex_request.get_rates(payload)

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

    def fedex_send_shipping(self, pickings):
        """
        Send FedEx shipment request for the given pickings.
        """
        fedex_request = FedExRequest(
            client_id=self.fedex_client_id,
            client_secret=self.fedex_client_secret,
            prod=self.prod_environment,
        )

        result = []
        for picking in pickings:
            payload = self._prepare_fedex_shipment_data(picking)
            shipment_data = fedex_request.create_shipment(payload)["output"][
                "transactionShipments"
            ][0]

            price = shipment_data["completedShipmentDetail"]["shipmentRating"][
                "shipmentRateDetails"
            ][1]["totalNetChargeWithDutiesAndTaxes"]

            master_tracking_number = shipment_data["masterTrackingNumber"]

            packs_label_data = []
            for pack_label_data in shipment_data["pieceResponses"]:
                pack = picking.package_ids.filtered(
                    lambda p: p.sequence == pack_label_data["packageSequenceNumber"]
                )

                label_filename = _(
                    "fedex_label_%(seq_number)s.zpl",
                    seq_number=pack_label_data["packageSequenceNumber"],
                )
                label_binary = base64.b64encode(
                    self._prepare_fedex_zpl_godex(
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

    def fedex_cancel_shipment(self, pickings):
        """
        Cancel FedEx shipments for the given pickings.
        """
        fedex_request = FedExRequest(
            client_id=self.fedex_client_id,
            client_secret=self.fedex_client_secret,
            prod=self.prod_environment,
        )

        res = True
        for picking in pickings.filtered("carrier_tracking_ref"):
            payload = {
                "accountNumber": {"value": str(self.fedex_account_number)},
                "senderCountryCode": picking.company_id.partner_id.country_id.code,
                "deletionControl": "DELETE_ALL_PACKAGES",
                "trackingNumber": picking.carrier_tracking_ref,
                "carrierCode": self.carrier_code,
            }
            res = res and fedex_request.cancel_shipment(payload)["output"].get(
                "cancelledShipment", False
            )

        return res

    def fedex_tracking_state_update(self, picking):
        """Tracking state update"""
        self.ensure_one()
        if not picking.carrier_tracking_ref:
            return

        fedex_request = FedExRequest(
            client_id=self.fedex_client_id,
            client_secret=self.fedex_client_secret,
            prod=self.prod_environment,
        )

        payload = {
            "includeDetailedScans": True,
            "trackingInfo": [
                {
                    "trackingNumberInfo": {
                        "trackingNumber": 882287670951,  # picking.carrier_tracking_ref,
                        "carrierCode": self.carrier_code,
                    },
                }
            ],
        }

        response = fedex_request.tracking_state_update(payload)["output"][
            "completeTrackResults"
        ][0]

        if response["trackingNumber"] != picking.carrier_tracking_ref:
            raise UserError(
                _(
                    "Tracking number mismatch: %(incoming_track)s != %(picking_track)s",
                    incoming_track=response["trackingNumberInfo"]["trackingNumber"],
                    picking_track=picking.carrier_tracking_ref,
                )
            )

        tracking_events = response["trackResults"][0]["scanEvents"]

        picking.shipping_number = response["trackingNumberInfo"]["trackingNumber"]

        picking.tracking_state_history = [
            _(
                "%(time)s %(date)s - [%(status_code)s] %(event)s\n"
                "Location       : %(city)s, %(state)s, %(country)s\n"
                "Address        : %(address)s, %(postal)s\n"
                "Location ID    : %(location_id)s\n"
                "Location Type  : %(location_type)s\n"
                "Status         : %(status)s (%(event_type)s)\n"
                "Exception      : %(exception)s (Code: %(exception_code)s)\n"
                "Delay          : %(delay_status)s due to "
                "%(delay_type)s (%(delay_sube)s)",
                time=datetime.fromisoformat(e["date"]).strftime("%H:%M:%S"),
                date=datetime.fromisoformat(e["date"]).strftime("%d/%m/%Y"),
                status_code=e["derivedStatusCode"],
                event=e["eventDescription"],
                city=e["scanLocation"]["city"],
                state=e["scanLocation"]["stateOrProvinceCode"],
                country=e["scanLocation"]["countryName"],
                address=", ".join(e["scanLocation"]["streetLines"]),
                postal=e["scanLocation"]["postalCode"],
                location_id=e["locationId"],
                location_type=e["locationType"],
                status=e["derivedStatus"],
                event_type=e["eventType"],
                exception=e["exceptionDescription"],
                exception_code=e["exceptionCode"],
                delay_status=e["delayDetail"]["status"],
                delay_type=e["delayDetail"]["type"],
                delay_sube=e["delayDetail"]["subType"],
            )
            for e in tracking_events
        ]

        carrier_received_by = response["trackResults"][0]["deliveryDetails"][
            "signedByName"
        ]

        date_delivered = next(
            (
                d["dateTime"]
                for d in response["trackResults"][0]["dateAndTimes"]
                if d["type"] == "ACTUAL_DELIVERY"
            ),
            None,
        )

        picking.carrier_received_by = carrier_received_by or picking.partner_id.name
        picking.date_delivered = (
            datetime.fromisoformat(date_delivered).strftime("%Y-%m-%d %H:%M:%S")
            if date_delivered
            else False
        )

        return True
