# Copyright 2025 Erol Develi (https://github.com/erlinberg)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import phonenumbers

from odoo import _, fields, models

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


class DeliveryCarrier(models.Model):
    _inherit = "delivery.carrier"
    delivery_type = fields.Selection(
        selection_add=[("fedex", "FedEx")],
        ondelete={"fedex": "set default"},
    )
    fedex_client_id = fields.Char(string="Client ID", help="FedEx Client ID")
    fedex_client_secret = fields.Char(
        string="Client Secret", help="FedEx Client Secret"
    )
    fedex_account_number = fields.Integer(
        string="Account Number", help="FedEx Account Number"
    )

    service_type = fields.Selection(selection=FEDEX_SERVICES)
    pickup_type = fields.Selection(selection=FEDEX_PICKUP_TYPES)
    customs_payment_type = fields.Selection(
        selection=FEDEX_PAYMENT_TYPES,
    )

    carrier_code = fields.Selection(selection=FEDEX_CARRIER_CODE)

    def _prepare_fedex_address(self, partner):
        return {
            "streetLines": [partner.street],
            "city": partner.city,
            "postalCode": partner.zip,
            "countryCode": partner.country_id.code,
            "residential": False,
        }

    def _prepare_fedex_contact(self, partner):
        contact = {
            "personName": partner.name,
            "emailAddress": partner.email,
            "companyName": partner.commercial_partner_id.name,
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

    def _prepare_fedex_packages_data(self, order):
        packages = []

        if order.picking_ids:
            pass

        else:
            # Create dummy pickings with order's deci
            deci = order.sale_deci * self._get_dimension_factor(order.sale_deci)
            average_pack_weight = 30
            pack_weight_threshold = 5

            # Calculate average weighted package count
            # and create them excluding the remainder
            avg_weighted_package_count = int(deci // average_pack_weight)

            for _ in range(avg_weighted_package_count):
                packages.append(
                    {
                        "weight": {"units": "KG", "value": average_pack_weight},
                    }
                )

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

    def _prepare_fedex_commodities_data(
        self, product, quantity, customs_value, customs_currency, weight
    ):
        return {
            "customsValue": {
                "currency": customs_currency,
                "amount": customs_value,
            },
            "unitPrice": {
                "currency": customs_currency,
                "amount": customs_value / quantity,
            },
            "description": product.categ_id.hs_code_id.description,
            "name": product.name,
            "countryOfManufacture": product.country_of_origin.code or "TR",
            "quantity": quantity,
            "harmonizedCode": product.categ_id.hs_code_id.hs_code,
            "quantityUnits": "Ea",
            "weight": {
                "units": "KG",
                "value": weight,
            },
        }

    def get_estimated_weight_from_order_line(self, order_line):
        return order_line.product_id.weight * order_line.qty_to_deliver

    def _prepare_sales_customs_data(self, order):
        data = self._prepare_fedex_base_customs_data(order.company_id, order.partner_id)

        data["commercialInvoice"] = {
            "purpose": order.order_id.fedex_shipment_purpose,
        }

        order.ensure_one()
        for order_line in order._get_lines_impacting_invoice_status():
            if order_line._is_not_sellable_line():
                continue

            data["commodities"].append(
                self._prepare_fedex_commodities_data(
                    order_line.product_id,
                    order_line.qty_to_deliver,
                    order_lines.customs_value
                    / len(order_lines._get_lines_impacting_invoice_status()),
                    order_lines.customs_value_currency_id.name,
                    self.get_estimated_weight_from_order_line(order_line),
                )
            )

        return data

    def _prepare_order_customs_data(self, picking, shipping_weight):
        data = self._prepare_fedex_base_customs_data(
            picking.company_id, picking.partner_id
        )

        data["commercialInvoice"] = {
            "purpose": picking.sale_id.fedex_shipment_purpose,
        }

        non_delivery_lines = picking.sale_id.order_line.filtered(
            lambda ol: not ol.is_delivery
        )

        for ol in non_delivery_lines:
            data["commodities"].append(
                self._prepare_fedex_commodities_data(
                    ol.product_id,
                    ol.product_uom_qty,
                    ol.price_subtotal,
                    picking.sale_id.currency_id.name,
                    shipping_weight / len(non_delivery_lines),
                )
            )

        total_customs_value = sum(non_delivery_lines.mapped("price_subtotal"))

        data["totalCustomsValue"] = {
            "currency": picking.sale_id.currency_id.name,
            "amount": total_customs_value,
        }

        return data

    def _prepare_base_rate_data(self, company_id, partner_id, delivery_date):
        return {
            "accountNumber": {"value": str(self.fedex_account_number)},
            "requestedShipment": {
                "shipper": {"address": self._prepare_fedex_address(company_id)},
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

    def _prepare_sales_rate_data(self, order):
        data = self._prepare_base_rate_data(
            order.company_id, order.partner_id, order.expected_date
        )

        data["requestedShipment"]["requestedPackageLineItems"] = (
            self._prepare_fedex_packages_data(order)
        )
        # data["requestedShipment"]["customsClearanceDetail"] = (
        #     self._prepare_sales_customs_data(order)
        # )

        return data

    def _prepare_account_rate_data(self, account_move):
        data = self._prepare_base_rate_data(
            account_move.company_id, account_move.partner_id, account_move.invoice_date
        )

        packages = self._prepare_fedex_packages_data(account_move.picking_ids)

        total_weight = 0
        for picking in account_move.picking_ids:
            total_weight += sum([pack.shipping_weight for pack in picking.package_ids])

        data["requestedShipment"]["totalWeight"] = total_weight
        data["requestedShipment"]["requestedPackageLineItems"] = packages
        data["requestedShipment"]["customsClearanceDetail"] = (
            self._prepare_account_customs_data(account_move.picking_ids)
        )

        return data

    def _prepare_shipment_data(self, picking):
        base_data = {
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
                    "labelPrintingOrientation": "BOTTOM_EDGE_OF_TEXT_FIRST",
                    "imageType": "ZPLII",
                    "labelStockType": "STOCK_4X6",
                    "resolution": 300,
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

        base_data["requestedShipment"]["customsClearanceDetail"] = (
            self._prepare_order_customs_data(picking, total_weight)
        )
        base_data["requestedShipment"]["requestedPackageLineItems"] = packages

        base_data["requestedShipment"]["totalPackageCount"] = len(packages)

        return base_data

    def fedex_rate_shipment(self, order):
        fedex_request = FedExRequest(
            client_id=self.fedex_client_id,
            client_secret=self.fedex_client_secret,
            prod=self.prod_environment,
        )
        payload = self._prepare_sales_rate_data(order)
        rate_data = fedex_request.get_rates(payload)

        price = rate_data.get("price")

        if rate_data.get("currency") != order.currency_id.name:
            currency = self.env["res.currency"].search(
                [("name", "=", rate_data.get("currency"))], limit=1
            )

            price = currency._convert(
                price,
                order.currency_id,
                order.company_id,
                order.date_order or fields.Date.today(),
            )

        result = {
            "success": True,
            "price": price,
            "error_message": False,
            "warning_message": False,
        }

        return result

    def fedex_account_rate_shipment(self, account_move):
        fedex_request = FedExRequest(
            client_id=self.fedex_client_id,
            client_secret=self.fedex_client_secret,
            prod=self.prod_environment,
        )
        payload = self._prepare_account_rate_data(account_move)
        rate_data = fedex_request.get_rates(payload)

        self.env["account.move.line"].create(
            {
                "move_id": account_move.id,
                "name": self.product_id.name,
                "quantity": 1,
                "price_unit": rate_data.get("price"),
                "product_id": account_move.carrier_id.product_id.id,
            }
        )

    def fedex_send_shipping(self, pickings):
        fedex_request = FedExRequest(
            client_id=self.fedex_client_id,
            client_secret=self.fedex_client_secret,
            prod=self.prod_environment,
        )

        result = []
        for picking in pickings:
            payload = self._prepare_shipment_data(picking)
            shipment_data = fedex_request.create_shipment(payload)["output"][
                "transactionShipments"
            ][0]

            price = shipment_data["completedShipmentDetail"]["shipmentRating"][
                "shipmentRateDetails"
            ][1]["totalNetChargeWithDutiesAndTaxes"]

            master_tracking_number = shipment_data["masterTrackingNumber"]

            attachments = []
            for package in shipment_data["pieceResponses"]:
                attachments.append(
                    (
                        f"fedex_label_{package['trackingNumber']}.zpl",
                        package["packageDocuments"][0]["encodedLabel"],
                    )
                )

            if attachments:
                body = _("Schenker Shipping barcode document")
                picking.message_post(body=body, attachments=attachments)

            result.append(
                {
                    "exact_price": price,
                    "tracking_number": master_tracking_number,
                }
            )

        return result

    def fedex_cancel_shipment(self, pickings):
        fedex_request = FedExRequest(
            client_id=self.fedex_client_id,
            client_secret=self.fedex_client_secret,
            prod=self.prod_environment,
        )

        for picking in pickings.filtered("carrier_tracking_ref"):
            payload = {
                "accountNumber": {"value": str(self.fedex_account_number)},
                "senderCountryCode": picking.company_id.partner_id.country_id.code,
                "deletionControl": "DELETE_ALL_PACKAGES",
                "trackingNumber": picking.carrier_tracking_ref,
                "carrierCode": self.carrier_code,
            }
            res = fedex_request.cancel_shipment(payload)["output"]

            return res.get("cancelledShipment", False)
