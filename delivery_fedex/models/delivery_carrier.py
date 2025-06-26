from odoo import fields, models

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
            "companyName": partner.name,
        }

        if partner.phone:
            contact["phoneNumber"] = partner.phone

        return contact

    def _prepare_fedex_packages_data(self, order):
        packages = []

        if order.picking_ids:
            pass

        else:
            # Create dummy pickings with order's deci
            deci = order.sale_deci
            average_pack_weight = 30
            package_count = (
                int(deci // average_pack_weight) or 1
            )  # At least one package

            for _ in range(package_count):
                packages.append(
                    {
                        "weight": {"units": "KG", "value": average_pack_weight},
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
                            else str(self.customer_fedex_number)
                        },
                        "contact": self._prepare_fedex_contact(company_id)
                        if self.customs_payment_type == "SENDER"
                        else self._prepare_fedex_contact(partner_id),
                        "address": self._prepare_fedex_address(company_id)
                        if self.customs_payment_type == "SENDER"
                        else self._prepare_fedex_address(partner_id),
                    }
                },
            },
            "commodities": [],
            "commercialInvoice": {
                "purpose": self.shipment_purpose,
            },
        }

    def _prepare_fedex_commodities_data(
        self, product, quantity, customs_value, customs_currency, shipping_weight
    ):
        return {
            "customsValue": {
                "currency": customs_currency,
                "amount": str(customs_value),
            },
            "unitPrice": {
                "currency": customs_currency,
                "amount": customs_value / quantity,
            },
            "description": product.name,
            "name": product.name,
            "countryOfManufacture": product.country_of_origin.code,
            "quantity": quantity,
            "harmonizedCode": product.hs_code,
            "quantityUnits": FEDEX_UOM_CODES[product.uom_name],
            "weight": {"units": "KG", "value": shipping_weight},
        }

    def get_estimated_weight_from_order_line(self, order_line):
        return order_line.product_id.weight * order_line.qty_to_deliver

    def _prepare_sales_customs_data(self, order_lines):
        data = self._prepare_fedex_base_customs_data(
            order_lines.company_id, order_lines.partner_id
        )

        order_lines.ensure_one()
        for order_line in order_lines._get_lines_impacting_invoice_status():
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

    def _prepare_account_customs_data(self, pickings):
        data = self._prepare_fedex_base_customs_data(
            pickings.company_id, pickings.partner_id
        )

        for picking in pickings:
            if picking.invoice_state == "2binvoiced":
                continue

            for package in picking.package_ids:
                customs_value = picking.invoice_ids.invoice_line_ids.filtered(
                    lambda invoice_line, picking=picking: invoice_line.product_id
                    != picking.carrier_id.product_id
                )
                customs_value = customs_value.price_subtotal
                data["commodities"].append(
                    self._prepare_fedex_commodities_data(
                        picking.move_ids[0].product_id,
                        picking.move_ids[0].quantity_done,
                        customs_value,
                        picking.invoice_ids.currency_id.name,
                        package.shipping_weight,
                    )
                )

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
        #     self._prepare_sales_customs_data(pickings)
        # )

        return data

    def _prepare_account_rate_data(self, account_move):
        data = self._prepare_base_rate_data(
            account_move.company_id, account_move.partner_id, account_move.invoice_date
        )

        packages = self._prepare_fedex_packages_data(account_move.picking_ids)

        total_weight = 0
        for picking in account_move.picking_ids:
            if picking.invoice_state == "2binvoiced":
                continue
            total_weight += sum([pack.shipping_weight for pack in picking.package_ids])

        data["requestedShipment"]["totalWeight"] = total_weight
        data["requestedShipment"]["requestedPackageLineItems"] = packages
        data["requestedShipment"]["customsClearanceDetail"] = (
            self._prepare_account_customs_data(account_move.picking_ids)
        )

        return data

    def _prepare_shipment_data(self, pickings):
        base_data = {
            "accountNumber": {"value": str(self.fedex_account_number)},
            "shipAction": "CONFIRM",
            "requestedShipment": {
                "shipper": {
                    "address": self._prepare_fedex_address(pickings.company_id),
                    "contact": self._prepare_fedex_contact(pickings.company_id),
                },
                "origin": {
                    "address": self._prepare_fedex_address(pickings.company_id),
                    "contact": self._prepare_fedex_contact(pickings.company_id),
                },
                "soldTo": {
                    "address": self._prepare_fedex_address(pickings.partner_id),
                    "contact": self._prepare_fedex_contact(pickings.partner_id),
                },
                "recipients": [
                    {
                        "address": self._prepare_fedex_address(pickings.partner_id),
                        "contact": self._prepare_fedex_contact(pickings.partner_id),
                    }
                ],
                "serviceType": self.service_type,
                "preferredCurrency": pickings.company_id.currency_id.display_name,
                "shipTimestamp": pickings.date.strftime("%Y-%m-%d"),
                "rateRequestType": ["PREFERRED"],
                "pickupType": self.pickup_type,
                "packagingType": "YOUR_PACKAGING",
                "shippingChargesPayment": {
                    "paymentType": self.payment_type,
                    "payor": {
                        "responsibleParty": {
                            "address": self._prepare_fedex_address(pickings.company_id)
                            if self.payment_type == "SENDER"
                            else self._prepare_fedex_address(pickings.partner_id),
                            "accountNumber": {
                                "value": str(self.fedex_account_number)
                                if self.payment_type == "SENDER"
                                else str(self.customer_fedex_number)
                            },
                            "contact": self._prepare_fedex_contact(pickings.company_id)
                            if self.payment_type == "SENDER"
                            else self._prepare_fedex_contact(pickings.partner_id),
                        }
                    },
                },
                "customsClearanceDetail": {},
                "labelSpecification": {
                    "labelFormatType": "COMMON2D",
                    "imageType": "PDF",
                    "labelStockType": "PAPER_LETTER",
                },
                "requestedPackageLineItems": [],
            },
            "labelResponseOptions": "LABEL",
            "mergeLabelDocOption": "LABELS_AND_DOCS",
        }

        packages = []
        total_weight = 0
        for picking in pickings:
            if picking.invoice_state == "2binvoiced":
                continue

            for pack in picking.package_ids:
                packages.append(
                    {
                        "weight": {"units": "KG", "value": pack.shipping_weight},
                        "dimensions": {
                            "length": pack.package_type_id.packaging_length / 10,
                            "width": pack.package_type_id.width / 10,
                            "height": pack.package_type_id.height / 10,
                            "units": "CM",
                        },
                    }
                )

            total_weight += pack.shipping_weight

        base_data["requestedShipment"]["totalWeight"] = total_weight
        base_data["requestedShipment"]["customsClearanceDetail"] = (
            self._prepare_account_customs_data(pickings)
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

        result = {
            "success": True,
            "price": rate_data.get("price"),
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

    def fedex_account_send_shipment(self, pickings):
        fedex_request = FedExRequest(
            client_id=self.fedex_client_id,
            client_secret=self.fedex_client_secret,
            prod=self.prod_environment,
        )
        payload = self._prepare_shipment_data(pickings)
        shipment_data = fedex_request.create_shipment(payload)["output"][
            "transactionShipments"
        ][0]

        price = shipment_data["completedShipmentDetail"]["shipmentRating"][
            "shipmentRateDetails"
        ][1]["totalNetCharge"]

        master_tracking_number = shipment_data["masterTrackingNumber"]

        labels = []
        for package in shipment_data["pieceResponses"]:
            labels.append(
                {
                    "package_id": package["trackingNumber"],
                    "name": "Label",
                    "datas": package["packageDocuments"][0]["encodedLabel"],
                    "file_type": package["packageDocuments"][0]["docType"],
                    "tracking_number": package["trackingNumber"],
                }
            )

        pickings.tracking_ref = master_tracking_number
        pickings.exact_fedex_price = price

        pickings.send_to_shipper()

        return {
            "exact_price": price,
            "tracking_number": master_tracking_number,
            "labels": labels,
        }

    def fedex_send_shipping(self, pickings):
        return [
            {
                "exact_price": pickings.exact_fedex_price,
                "tracking_number": pickings.tracking_ref,
                "labels": None,
            }
        ]
