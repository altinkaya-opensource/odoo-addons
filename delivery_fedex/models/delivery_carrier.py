# Copyright 2025 Erol Develi (https://github.com/erlinberg)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import base64
import logging
from datetime import datetime

import phonenumbers

from odoo import _, fields, models
from odoo.exceptions import UserError

from .fedex_request import FedExRequest

FEDEX_SERVICES = [
    ("FEDEX_REGIONAL_ECONOMY", "Regional Economy"),
    ("INTERNATIONAL_ECONOMY", "International Economy"),
    ("INTERNATIONAL_FIRST", "International First"),
    ("FEDEX_INTERNATIONAL_PRIORITY", "International Priority"),
    ("FEDEX_INTERNATIONAL_PRIORITY_EXPRESS", "International Priority Express"),
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

FEDEX_TO_ODOO_STATUS = {
    # Shipping recorded in carrier
    "OC": "shipping_recorded_in_carrier",
    "OX": "shipping_recorded_in_carrier",
    "DO": "shipping_recorded_in_carrier",
    "PU": "shipping_recorded_in_carrier",
    "IP": "shipping_recorded_in_carrier",
    "HP": "shipping_recorded_in_carrier",
    "MD": "shipping_recorded_in_carrier",
    # In transit
    "IT": "in_transit",
    "AR": "in_transit",
    "AF": "in_transit",
    "AC": "in_transit",
    "PM": "in_transit",
    "DP": "in_transit",
    "CP": "in_transit",
    "EA": "in_transit",
    "TR": "in_transit",
    "CC": "in_transit",
    "CH": "in_transit",
    "IN": "in_transit",
    # Canceled shipment
    "CA": "canceled_shipment",
    "LC": "canceled_shipment",
    "RC": "canceled_shipment",
    # Incident / Exceptions
    "DD": "incident",
    "DE": "incident",
    "SE": "incident",
    "CD": "incident",
    "DY": "incident",
    "DR": "incident",
    "PD": "incident",
    "RD": "incident",
    "RG": "incident",
    # Customer delivered
    "DL": "customer_delivered",
    "OD": "customer_delivered",
    # No more updates from carrier
    "RS": "no_update",
    "RP": "no_update",
    "DS": "no_update",
    "US": "no_update",
    "AE": "no_update",
    "AO": "no_update",
    "RR": "no_update",
    "RM": "no_update",
    "HA": "no_update",
    "RT": "no_update",
    "RA": "no_update",
    "PR": "no_update",
    "AS": "no_update",
}

FEDEX_LABEL_STOCK_SELECTION = [
    ("PAPER_4X6", "PAPER_4X6"),
    ("STOCK_4X675", "STOCK_4X675"),
    ("PAPER_4X675", "PAPER_4X675"),
    ("PAPER_4X8", "PAPER_4X8"),
    ("PAPER_4X9", "PAPER_4X9"),
    ("PAPER_7X475", "PAPER_7X475"),
    ("PAPER_85X11_BOTTOM_HALF_LABEL", "PAPER_85X11_BOTTOM_HALF_LABEL"),
    ("PAPER_85X11_TOP_HALF_LABEL", "PAPER_85X11_TOP_HALF_LABEL"),
    ("PAPER_LETTER", "PAPER_LETTER"),
    ("STOCK_4X675_LEADING_DOC_TAB", "STOCK_4X675_LEADING_DOC_TAB"),
    ("STOCK_4X8", "STOCK_4X8"),
    ("STOCK_4X9_LEADING_DOC_TAB", "STOCK_4X9_LEADING_DOC_TAB"),
    ("STOCK_4X6", "STOCK_4X6"),
    ("STOCK_4X675_TRAILING_DOC_TAB", "STOCK_4X675_TRAILING_DOC_TAB"),
    ("STOCK_4X9_TRAILING_DOC_TAB", "STOCK_4X9_TRAILING_DOC_TAB"),
    ("STOCK_4X9", "STOCK_4X9"),
    ("STOCK_4X85_TRAILING_DOC_TAB", "STOCK_4X85_TRAILING_DOC_TAB"),
    ("STOCK_4X105_TRAILING_DOC_TAB", "STOCK_4X105_TRAILING_DOC_TAB"),
]


_logger = logging.getLogger(__name__)


def normalize_turkish(text):
    """
    Normalize Turkish characters to their English equivalents.
    This is necessary because FedEx API's labels does not support Turkish
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
        selection_add=[("fedex", "FedEx")],
        ondelete={"fedex": "set default"},
    )

    # FedEx uses different client IDs and secrets for different services
    # and tracking, so we need to store them separately.
    fedex_client_id = fields.Char(string="Client ID", help="FedEx Client ID")
    fedex_client_secret = fields.Char(help="FedEx Client Secret")

    fedex_tracking_client_id = fields.Char(help="FedEx Tracking Client ID")
    fedex_tracking_client_secret = fields.Char(help="FedEx Tracking Client Secret")

    fedex_account_number = fields.Integer(help="FedEx Account Number")

    fedex_commercial_invoice = fields.Many2one(
        "ir.actions.report",
        string="FedEx Commercial Invoice",
        help="FedEx Commercial Invoice report to be used for shipments.",
    )

    service_type = fields.Selection(selection=FEDEX_SERVICES)
    pickup_type = fields.Selection(selection=FEDEX_PICKUP_TYPES)
    customs_payment_type = fields.Selection(
        selection=FEDEX_PAYMENT_TYPES,
    )

    carrier_code = fields.Selection(selection=FEDEX_CARRIER_CODE)

    label_paper_type = fields.Selection(
        selection=FEDEX_LABEL_STOCK_SELECTION,
        default="PAPER_85X11_TOP_HALF_LABEL",
        help="Label paper type for FedEx shipments.",
    )

    label_resolution = fields.Integer(
        default=203,
        help="Label resolution in DPI for FedEx shipments. "
        "This is used only for ZPL labels.",
    )

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
        street_lines = []
        address_lines = normalize_turkish(
            f"{partner.street or ''} {partner.street2 or ''}"
        )

        # Split address spaces into lines which have a maximum length of 35 characters
        address_words = address_lines.split()
        text_line = ""
        for word in address_words:
            if len(text_line + " " + word) <= 35:
                text_line += " " + word
            else:
                street_lines.append(text_line.strip())
                text_line = word

        if text_line:
            street_lines.append(text_line.strip())

        return {
            "streetLines": street_lines,
            "city": normalize_turkish(partner.city or partner.state_id.name or ""),
            "postalCode": partner.zip,
            "countryCode": partner.country_id.code,
            "residential": False,  # TODO: Maybe this need to be dynamic?
        }

    def _prepare_fedex_contact(self, partner):
        """
        Prepare FedEx contact data from partner.
        """
        contact = {
            "personName": normalize_turkish(partner.name or ""),
            "emailAddress": partner.email,
            "companyName": normalize_turkish(partner.commercial_partner_id.name or ""),
        }

        if partner.phone or partner.mobile:
            # Use phonenumbers library to format the phone number
            # for FedEx API
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

    def _prepare_fedex_base_customs_data(self, warehouse_id, partner_id):
        """
        Prepare base customs data for FedEx shipments.
        """
        data = {
            "dutiesPayment": {
                "paymentType": self.customs_payment_type,
            },
            "commodities": [],
        }

        if self.customs_payment_type == "SENDER":
            data["dutiesPayment"]["payor"] = {
                "responsibleParty": {
                    "address": self._prepare_fedex_address(warehouse_id.partner_id),
                    "accountNumber": {"value": str(self.fedex_account_number)},
                    "contact": self._prepare_fedex_contact(warehouse_id.partner_id),
                },
            }

        return data

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
            picking.location_id.warehouse_id, picking.partner_id
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
            "amount": max(
                sum(lines_to_ship.mapped("price_subtotal")), 1.0
            ),  # Some countries require a minimum customs value
        }

        return data

    def _prepare_fedex_base_rate_data(self, warehouse_id, partner_id, delivery_date):
        """
        Prepare base rate data for FedEx API requests.
        """
        return {
            "accountNumber": {"value": str(self.fedex_account_number)},
            "requestedShipment": {
                "shipper": {
                    "address": self._prepare_fedex_address(warehouse_id.partner_id)
                },
                "recipient": {"address": self._prepare_fedex_address(partner_id)},
                "serviceType": self.service_type,
                "preferredCurrency": self.currency_id.name,
                "rateRequestType": ["ACCOUNT"],
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
            order.warehouse_id, order.partner_id, fields.Date.today()
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
            account_move.picking_ids.location_id.warehouse_id,
            account_move.partner_shipping_id,
            fields.Date.today(),
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

        data["requestedShipment"]["requestedPackageLineItems"] = packages
        data["requestedShipment"]["totalPackageCount"] = len(packages)

        return data

    def _upload_fedex_commercial_invoice(self, picking):
        data = {
            "workflowName": "ETDPreshipment",
            "carrierCode": self.carrier_code,
            "originCountryCode": (
                picking.location_id.warehouse_id.partner_id.country_id.code
            ),
            "destinationCountryCode": picking.partner_id.country_id.code,
            "shipmentDate": fields.Date.today().strftime("%Y-%m-%d") + "T12:00:00",
            "metaData": [
                {
                    "fileReferenceId": picking.name + "commercial_invoice",
                    "shipDocumentType": "COMMERCIAL_INVOICE",
                    "contentType": "application/pdf",
                }
            ],
        }

        if not self.fedex_commercial_invoice:
            raise UserError(
                _("FedEx Commercial Invoice report is not configured for this carrier.")
            )

        if self.fedex_commercial_invoice.report_type == "py3o":
            data["metaData"][0]["fileContentBase64"] = base64.b64encode(
                self.env["ir.actions.report"]._render_py3o(
                    self.fedex_commercial_invoice.report_name,
                    res_ids=picking.invoice_ids.filtered(lambda m: m.state == "posted")[
                        0
                    ].ids,
                )[0]
            ).decode("utf-8")
        else:
            data["metaData"][0]["fileContentBase64"] = base64.b64encode(
                self.env["ir.actions.report"]._render_qweb_pdf(
                    self.fedex_commercial_invoice.report_name,
                    res_ids=picking.invoice_ids.filtered(lambda m: m.state == "posted")[
                        0
                    ].ids,
                )[0]
            ).decode("utf-8")

        fedex_request = FedExRequest(
            client_id=self.fedex_client_id,
            client_secret=self.fedex_client_secret,
            delivery_carrier=self,
            prod=self.prod_environment,
        )

        document_id = None
        try:
            response = fedex_request.upload_documents(data=data)
            document_id = response["output"]["documentResponses"]["metaData"]["docId"]
        except Exception as e:
            raise UserError(
                _(
                    "Failed to upload the Electronic"
                    " Trade Document for FedEx shipment: %s{error_message}",
                    error_message=e,
                )
            ) from e

        return document_id

    def _prepare_fedex_shipment_data(self, picking):
        """
        Prepare shipment data for FedEx API requests
        based on the stock picking.
        """

        # Prepare the commercial invoice
        # document_id = self._upload_fedex_commercial_invoice(picking)
        # if document_id is None:
        #     raise UserError(
        #         _(
        #             "Failed to prepare and upload the Electronic Trade Document "
        #             "for FedEx shipment."
        #         )
        #     )

        data = {
            "accountNumber": {"value": str(self.fedex_account_number)},
            "shipAction": "CONFIRM",
            "requestedShipment": {
                "shipper": {
                    "address": self._prepare_fedex_address(
                        picking.location_id.warehouse_id.partner_id
                    ),
                    "contact": self._prepare_fedex_contact(
                        picking.location_id.warehouse_id.partner_id
                    ),
                },
                "origin": {
                    "address": self._prepare_fedex_address(
                        picking.location_id.warehouse_id.partner_id
                    ),
                    "contact": self._prepare_fedex_contact(
                        picking.location_id.warehouse_id.partner_id
                    ),
                },
                "soldTo": {
                    "address": self._prepare_fedex_address(picking.partner_id),
                    "contact": self._prepare_fedex_contact(picking.partner_id),
                },
                "recipients": [
                    {
                        "address": self._prepare_fedex_address(picking.partner_id),
                        "contact": self._prepare_fedex_contact(picking.partner_id),
                    }
                ],
                "serviceType": self.service_type,
                "preferredCurrency": self.currency_id.name,
                "shipDatestamp": picking.date.strftime("%Y-%m-%d"),
                "pickupType": self.pickup_type,
                "packagingType": "YOUR_PACKAGING",
                "shippingChargesPayment": {
                    "paymentType": "SENDER"
                    if self.payment_type == "sender_pays"
                    else "RECIPIENT",
                    "payor": {
                        "responsibleParty": {
                            "address": self._prepare_fedex_address(
                                picking.location_id.warehouse_id.partner_id
                            )
                            if self.payment_type == "sender_pays"
                            else self._prepare_fedex_address(
                                picking.location_id.warehouse_id.partner_id
                            ),
                            "accountNumber": {
                                "value": str(self.fedex_account_number)
                                if self.payment_type == "sender_pays"
                                else (
                                    picking.partner_id.commercial_partner_id.fedex_customer_number
                                )
                            },
                            "contact": self._prepare_fedex_contact(
                                picking.location_id.warehouse_id.partner_id
                            )
                            if self.payment_type == "sender_pays"
                            else self._prepare_fedex_contact(picking.partner_id),
                        }
                    },
                },
                "customsClearanceDetail": {},
                "labelSpecification": {
                    "labelFormatType": "COMMON2D",
                    "imageType": "PDF"
                    if self.carrier_barcode_type == "pdf"
                    else "ZPLII",
                    "labelStockType": self.label_paper_type,
                    "resolution": self.label_resolution
                    if self.carrier_barcode_type == "zpl"
                    else 203,
                },
                "requestedPackageLineItems": [],
                # "shipmentSpecialServices": {
                #     "specialServiceTypes": ["ELECTRONIC_TRADE_DOCUMENTS"],
                #     "etdDetail": {
                #         "attachedDocuments": [
                #             {
                #                 "documentType": "COMMERCIAL_INVOICE",
                #                 "documentId": document_id,
                #             }
                #         ]
                #     },
                # },
            },
            "labelResponseOptions": "LABEL",
            # Add the commercial invoice details
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
        """
        Prepare FedEx API's ZPL for GoDEX printer.
        This method modifies the ZPL to fit the GoDEX printer requirements.
        """
        res = binary_zpl.decode("utf-8").replace(
            "^CF,0,0,0^PR12^MD30^PW1200^POI^CI13^LH0,20", ""
        )

        # height = real size in inches * DPI (300)
        res = res.replace("^XA", f"^XA^LL{int(self.stock_height * 300)}")

        return res.encode("utf-8")

    def _format_rate_data(self, data):
        rate_details = data["output"]["rateReplyDetails"][0]["ratedShipmentDetails"]

        account_rate_detail = next(
            (rd for rd in rate_details if rd.get("rateType") == "ACCOUNT"),
            None,
        )
        if not account_rate_detail:
            raise UserError(_("FedEx rate data does not contain account rate details."))

        return {
            "price": account_rate_detail["totalNetChargeWithDutiesAndTaxes"],
            "currency": account_rate_detail["currency"],
        }

    def fedex_rate_shipment(self, order):
        """
        Get FedEx rate for the given sale order.
        """
        fedex_request = FedExRequest(
            client_id=self.fedex_client_id,
            client_secret=self.fedex_client_secret,
            delivery_carrier=self,
            prod=self.prod_environment,
        )
        payload = self._prepare_fedex_sale_rate_data(order)

        try:
            response = fedex_request.get_rates(payload)

            rate_data = self._format_rate_data(response)
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
        except Exception as __:  # This means there is no rate or the request failed
            price = 0.0

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
        if self.payment_type == "customer_pays":
            raise UserError(
                _(
                    "You cannot get rates for an invoice with 'Customer Pays' "
                    "payment type."
                )
            )

        if not account_move.picking_ids:
            raise UserError(_("Cannot get rates for an invoice without pickings."))

        fedex_request = FedExRequest(
            client_id=self.fedex_client_id,
            client_secret=self.fedex_client_secret,
            delivery_carrier=self,
            prod=self.prod_environment,
        )
        payload = self._prepare_fedex_account_rate_data(account_move)
        response = fedex_request.get_rates(payload)

        rate_data = self._format_rate_data(response)
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
        if (
            self.payment_type == "customer_pays"
            and not pickings.partner_id.fedex_customer_number
        ):
            raise UserError(
                _(
                    "FedEx customer number is required for the recipient when "
                    "the payment type is set to 'Customer Pays'."
                )
            )

        fedex_request = FedExRequest(
            client_id=self.fedex_client_id,
            client_secret=self.fedex_client_secret,
            delivery_carrier=self,
            prod=self.prod_environment,
        )

        result = []
        for picking in pickings:
            payload = self._prepare_fedex_shipment_data(picking)
            response = fedex_request.create_shipment(payload)

            shipment_data = response["output"]["transactionShipments"][0]

            master_tracking_number = shipment_data["masterTrackingNumber"]

            self.fedex_request_pickup(
                picking,
                sum(pack.shipping_weight for pack in picking.package_ids),
                master_tracking_number,
            )

            price = 0.0

            if self.payment_type != "customer_pays" and shipment_data[
                "completedShipmentDetail"
            ].get("shipmentRating"):
                shipment_rate_details = shipment_data["completedShipmentDetail"][
                    "shipmentRating"
                ]["shipmentRateDetails"][0]

                price = shipment_rate_details["totalNetChargeWithDutiesAndTaxes"]

                picking.carrier_shipping_cost = shipment_rate_details["totalBaseCharge"]
                picking.carrier_shipping_vat = shipment_rate_details["totalTaxes"]
                picking.carrier_shipping_total = shipment_rate_details[
                    "totalNetChargeWithDutiesAndTaxes"
                ]

                picking.carrier_total_deci = shipment_rate_details[
                    "totalBillingWeight"
                ]["value"]
            elif self.payment_type != "customer_pays" and not shipment_data[
                "completedShipmentDetail"
            ].get("shipmentRating"):
                _logger.error(
                    "FedEx shipment %s does not have shipment rating "
                    "information. Shipping cost will be set to 0.",
                    picking.name,
                )
                picking.carrier_shipping_cost = 0.0
                picking.carrier_shipping_vat = 0.0
                picking.carrier_shipping_total = 0.0
                picking.carrier_total_deci = 0.0

            for sequence, pack_label_data in enumerate(shipment_data["pieceResponses"]):
                label_filename = (
                    f"fedex_label_{picking.name}_{sequence}.{self.carrier_barcode_type}"
                )

                if self.carrier_barcode_type == "zpl":
                    label_content = base64.b64encode(
                        self._prepare_fedex_zpl_godex(
                            base64.b64decode(
                                pack_label_data["packageDocuments"][0]["encodedLabel"]
                            )
                        )
                    )
                else:
                    label_content = pack_label_data["packageDocuments"][0][
                        "encodedLabel"
                    ]

                self.env["ir.attachment"].create(
                    {
                        "name": label_filename,
                        "datas": label_content,
                        "res_model": "stock.picking",
                        "res_id": picking.id,
                        "is_delivery_document": True,
                    }
                )

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
            delivery_carrier=self,
            prod=self.prod_environment,
        )

        res = True
        for picking in pickings.filtered("carrier_tracking_ref"):
            if picking.delivery_state != "shipping_recorded_in_carrier":
                _logger.warning(
                    "Cannot cancel FedEx shipment for picking %s with state %s.",
                    picking.name,
                    picking.delivery_state,
                )
                continue  # TODO: Maybe raise an error instead?

            payload = {
                "accountNumber": {"value": str(self.fedex_account_number)},
                "senderCountryCode": (
                    picking.location_id.warehouse_id.partner_id.country_id.code
                ),
                "deletionControl": "DELETE_ALL_PACKAGES",
                "trackingNumber": picking.carrier_tracking_ref,
                "carrierCode": self.carrier_code,
            }
            response = fedex_request.cancel_shipment(payload)

            canceled = response["output"].get("cancelledShipment", False)

            if canceled:
                self.fedex_cancel_pickup(picking)

            res = res and canceled

        return res

    def fedex_tracking_state_update(self, picking):
        """Tracking state update"""
        self.ensure_one()
        if not picking.carrier_tracking_ref:
            return

        fedex_request = FedExRequest(
            client_id=self.fedex_tracking_client_id,
            client_secret=self.fedex_tracking_client_secret,
            delivery_carrier=self,
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

        response = fedex_request.tracking_state_update(payload)["output"][
            "completeTrackResults"
        ][0]

        picking.carrier_tracking_ref = response["trackingNumber"]
        picking.shipping_number = response["trackingNumber"]

        tracking_events = response["trackResults"][0]["scanEvents"]

        last_event = tracking_events[-1] if tracking_events else {}

        picking.delivery_state = FEDEX_TO_ODOO_STATUS.get(
            last_event.get("derivedStatusCode"), "shipping_recorded_in_carrier"
        )

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

        if not response["trackResults"][0].get("dateAndTimes"):
            picking.date_delivered = False
            return True

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

    def _prepare_fedex_pickup_data(
        self, picking, nearest_pickup, total_weight, tracking_number
    ):
        """
        Prepare FedEx pickup payload for the given picking.
        """
        warehouse_partner = picking.location_id.warehouse_id.partner_id

        return {
            "associatedAccountNumber": {"value": self.fedex_account_number},
            "carrierCode": self.carrier_code,
            "originDetail": {
                "pickupLocation": {
                    "contact": self._prepare_fedex_contact(warehouse_partner),
                    "address": self._prepare_fedex_address(warehouse_partner),
                },
                "readyDateTimestamp": nearest_pickup["date"]
                + "T"
                + nearest_pickup["time"],
                "customerCloseTime": "18:00:00",
                "pickupDateType": nearest_pickup["pickup_date_type"],
                "buildingType": "BUILDING",
            },
            "totalWeight": {
                "units": "KG",
                "value": total_weight,
            },
            "packageCount": len(picking.package_ids),
            # TODO: Make this configurable in the future.
            "countryRelationship": "INTERNATIONAL",
            "trackingNumber": tracking_number,
        }

    def _prepare_fedex_pickup_check_data(self, picking):
        """
        Prepare FedEx pickup check data for the given picking.
        """
        return {
            "carriers": [self.carrier_code],
            "pickupAddress": self._prepare_fedex_address(
                picking.location_id.warehouse_id.partner_id
            ),
            "pickupRequestType": ["SAME_DAY", "FUTURE_DAY"],
            "shipmentAttributes": {
                "serviceType": self.service_type,
            },
            # TODO: Make this configurable in the future.
            "countryRelationship": "INTERNATIONAL",
        }

    def get_nearest_available_fedex_pickup(self, picking):
        """
        Get nearest available pickup for the given pickings.
        """
        fedex_request = FedExRequest(
            client_id=self.fedex_client_id,
            client_secret=self.fedex_client_secret,
            delivery_carrier=self,
            prod=self.prod_environment,
        )

        payload = self._prepare_fedex_pickup_check_data(picking)
        response = fedex_request.check_pickup_availability(payload)

        options = response["output"]["options"]

        if not options:
            raise UserError(_("No available pickups found for the given pickings."))

        nearest_pickup = next(
            (opt for opt in options if opt.get("available")), options[0]
        )

        return {
            "date": nearest_pickup["pickupDate"],
            "time": nearest_pickup["readyTimeOptions"][0],
            "pickup_date_type": nearest_pickup["scheduleDay"],
        }

    def fedex_request_pickup(self, picking, total_weight, tracking_number):
        """
        Request a FedEx pickup for the given picking.
        """
        fedex_request = FedExRequest(
            client_id=self.fedex_client_id,
            client_secret=self.fedex_client_secret,
            delivery_carrier=self,
            prod=self.prod_environment,
        )

        nearest_pickup = self.get_nearest_available_fedex_pickup(picking=picking)

        payload = self._prepare_fedex_pickup_data(
            picking, nearest_pickup, total_weight, tracking_number
        )
        response = fedex_request.request_pickup(payload)

        if not response.get("output"):
            raise UserError(_("Failed to request FedEx pickup."))

        picking.invoice_ids.filtered(lambda m: m.state == "posted")[0].message_post(
            body=_(
                "FedEx pickup requested successfully on "
                "%(date)s at %(time)s.\n"
                "Pickup Confirmation Number: %(pickupNo)s",
                date=nearest_pickup["date"],
                time=nearest_pickup["time"],
                pickupNo=response["output"]["pickupConfirmationCode"],
            )
        )

        picking.fedex_pickup_confirmation_code = response["output"][
            "pickupConfirmationCode"
        ]
        picking.fedex_pickup_date = datetime.strptime(
            nearest_pickup["date"], "%Y-%m-%d"
        )
        picking.fedex_pickup_location = response["output"].get("location", False)

        return True

    def fedex_cancel_pickup(self, picking):
        """
        Cancel a FedEx pickup for the given picking.
        """
        fedex_request = FedExRequest(
            client_id=self.fedex_client_id,
            client_secret=self.fedex_client_secret,
            delivery_carrier=self,
            prod=self.prod_environment,
        )

        if not picking.fedex_pickup_confirmation_code:
            return True  # Nothing to cancel

        payload = {
            "associatedAccountNumber": {"value": str(self.fedex_account_number)},
            "carrierCode": self.carrier_code,
            "pickupConfirmationCode": picking.fedex_pickup_confirmation_code,
            "scheduledDate": picking.fedex_pickup_date.strftime("%Y-%m-%d"),
        }

        if self.carrier_code == "FDXE":
            payload["location"] = picking.fedex_pickup_location

        response = fedex_request.cancel_pickup(payload)

        if not response.get("output"):
            raise UserError(_("Failed to cancel FedEx pickup."))

        picking.invoice_ids[0].message_post(
            body=_(
                "FedEx pickup canceled successfully.\n"
                "Pickup Confirmation Number: %(pickupNo)s",
                pickupNo=response["output"]["pickupConfirmationCode"],
            )
        )

        return True

    def clear_delivery_data(self, picking):
        res = super().clear_delivery_data(picking)

        # Clear FedEx Pickup data
        picking.fedex_pickup_confirmation_code = False
        picking.fedex_pickup_date = False
        picking.fedex_pickup_location = False

        return res
