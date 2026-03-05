# Copyright 2025 Erol Develi (https://github.com/erlinberg)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import base64
import logging
from datetime import datetime, timedelta

import pytz

from odoo import _, fields, models
from odoo.exceptions import UserError

from .dhl_request import DHLRequest

DHL_SERVICES = [
    ("E", "Express 9:00"),
    ("Y", "Express 12:00"),
    ("P", "Express Worldwide"),
    ("H", "Economy Select"),
]

DHL_STATUS_CODE_MAP = {
    "PU": "in_transit",
    "PL": "in_transit",
    "AF": "in_transit",
    "DF": "in_transit",
    "AR": "in_transit",
    "WC": "in_transit",
    "CR": "in_transit",
    "RR": "in_transit",
    "OK": "customer_delivered",
}

UNECE_TO_DHL_UOM = {
    "KGM": "KG",
    "GRM": "GM",
    "CMT": "CM",
    "MTR": "M",
    "C62": "PCS",
}

_logger = logging.getLogger(__name__)


class DeliveryCarrier(models.Model):
    _inherit = "delivery.carrier"
    delivery_type = fields.Selection(
        selection_add=[("dhl", "DHL")],
        ondelete={"dhl": "set default"},
    )

    # DHL uses different client IDs and secrets for different services
    # and tracking, so we need to store them separately.
    dhl_api_key = fields.Char()
    dhl_api_secret = fields.Char()

    dhl_account_number = fields.Char(help="DHL Account Number")

    dhl_service_type = fields.Selection(selection=DHL_SERVICES)

    dhl_pickup_location = fields.Char()
    dhl_pickup_close_time = fields.Char()

    dhl_label_dpi = fields.Selection(
        selection=[("200", "200 DPI"), ("300", "300 DPI")],
        string="Label DPI",
        default="300",
        help="DPI for the ZPL DHL label.",
    )

    dhl_label_type = fields.Selection(
        selection=[
            ("pdf", "PDF"),
            ("zpl", "ZPL"),
        ],
        default="pdf",
        help="Label type for the DHL label.",
    )

    dhl_commercial_invoice = fields.Many2one(
        "ir.actions.report",
        help="DHL Commercial Invoice report to be used for shipments.",
    )

    # DHL limits the shipment description to 70 characters,
    dhl_general_shipment_description = fields.Char(
        default="",
        size=70,
        help="General shipment description to be used for DHL shipments.",
    )

    def _get_estimated_weight_from_order_line(self, order_line):
        return order_line.product_id.weight * order_line.qty_to_deliver

    def _prepare_dhl_address(self, partner):
        """
        Prepare DHL address data from partner.
        """
        address_data = {
            "postalCode": partner.zip or "",
            "cityName": partner.city or partner.state_id.name or "",
            "countryCode": partner.country_id.code or "TR",
            "addressLine1": partner.street or "",
        }

        if partner.street2:
            address_data["addressLine2"] = partner.street2

        return address_data

    def _prepare_dhl_contact(self, partner):
        """
        Prepare DHL contact data from partner.
        """
        contact_data = {
            "fullName": partner.name,
            "phone": partner.phone or partner.mobile,
            "companyName": partner.commercial_partner_id.name,
        }

        if partner.email:
            contact_data["email"] = partner.email

        return contact_data

    def _get_package_count(self, packages):
        """Return total package count considering package_multiplier."""
        return sum(p.package_multiplier for p in packages)

    def _prepare_dhl_dummy_packages(self, order):
        """
        Estimate and prepare dummy packages for DHL rate
        calculation.
        """
        if order.picking_ids:
            raise UserError(_("Cannot get rates for an order with existing pickings."))

        raw_packages = self._generate_dummy_packages(order.sale_deci)

        packages = []
        for pack in raw_packages:
            packages.append(
                {
                    "weight": pack["weight"],
                    "dimensions": pack["dimensions"],
                }
            )

        return packages

    def _prepare_dhl_custom_details_data(self, picking, shipping_weight):
        """
        Prepare estimated customs data for DHL
        shipments on the picking and shipping weight.
        """
        line_items = []
        invoice = picking.invoice_ids.filtered(lambda m: m.state == "posted")[0]
        # Get non-delivery lines from the sale order
        lines_to_ship = invoice.invoice_line_ids.filtered(
            lambda l: not l.product_id.default_code.startswith("KAR-PO")
        )

        average_line_weight = (
            shipping_weight / len(lines_to_ship) if lines_to_ship else 0.1
        )

        total_value = 0
        for seq, lts in enumerate(lines_to_ship):
            # DHL requires price and total declared value to
            # be a positive multiple of 0.001
            product_price = max(round(lts.price_subtotal / lts.quantity, 3), 0.001)
            total_value += product_price * int(lts.quantity)
            line_items.append(
                {
                    # DHL requires number to be a positive integer
                    "number": seq + 1,
                    "description": lts.product_id.categ_id.hs_code_id.with_context(
                        lang="en_US"
                    ).description
                    or lts.product_id.name,
                    "price": product_price,
                    "quantity": {
                        "value": int(lts.quantity),
                        "unitOfMeasurement": UNECE_TO_DHL_UOM.get(
                            lts.product_uom_id.unece_code, "PCS"
                        ),
                    },
                    "weight": {
                        "netValue": round(max(0.1, average_line_weight), 3),
                        "grossValue": round(max(0.1, average_line_weight), 3),
                    },
                    "manufacturerCountry": lts.product_id.country_of_origin.code
                    or "TR",
                    "commodityCodes": [
                        {
                            "value": lts.product_id.categ_id.hs_code_id.hs_code,
                            "typeCode": "outbound",
                        }
                    ],
                }
            )

        return max(round(total_value, 3), 0.1), line_items

    def _prepare_dhl_base_rate_data(self, company_id, partner_id, delivery_date_str):
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
                    "number": self.dhl_account_number,
                }
            ],
            "productsAndServices": [
                {
                    "productCode": self.dhl_service_type,
                }
            ],
            "plannedShippingDateAndTime": delivery_date_str,
            "unitOfMeasurement": "metric",
            "isCustomsDeclarable": True,
        }

    def _prepare_dhl_sale_rate_data(self, order):
        """
        Prepare rate data for DHL API requests
        based on the sale order.
        """
        data = self._prepare_dhl_base_rate_data(
            order.company_id,
            order.partner_id,
            self._prepare_dhl_estimated_pickup_date(),
        )

        # We use dummy packages because when getting rates
        # from sale.order we don't have actual packages yet.
        data["packages"] = self._prepare_dhl_dummy_packages(order)

        return data

    def _prepare_dhl_estimated_pickup_date(
        self, cutoff_hour=14, cut_off_margin_minutes=30
    ):
        """
        Prepare estimated pickup date for DHL API requests.
        The pickup date is calculated based on the current time,
        cutoff hour, and a margin to avoid issues with the cutoff time.
        """
        now_utc = fields.Datetime.now()

        cutoff_margin = timedelta(minutes=cut_off_margin_minutes)
        user_tz = pytz.timezone(self.env.user.tz or "UTC")
        now_local = pytz.utc.localize(now_utc).astimezone(user_tz)

        cutoff_time = (
            now_local.replace(hour=cutoff_hour, minute=0, second=0, microsecond=0)
            - cutoff_margin
        )

        if now_local < cutoff_time and self._is_tr_business_day(now_local):
            estimated = now_local.replace(
                hour=cutoff_hour, minute=0, second=0, microsecond=0
            )
        else:
            tomorrow = now_local + timedelta(days=1)
            estimated = self._get_next_tr_business_day(tomorrow).replace(
                hour=cutoff_hour, minute=0, second=0, microsecond=0
            )

        tz_str = estimated.strftime("%z")
        return estimated.strftime(f"%Y-%m-%dT%H:%M:%SGMT{tz_str[:3]}:{tz_str[3:]}")

    def _prepare_dhl_commercial_invoice_data(self, invoices):
        """
        Prepare commercial invoice data for DHL API requests
        based on the invoice.
        """
        if self.dhl_commercial_invoice.report_type == "py3o":
            return base64.b64encode(
                self.env["ir.actions.report"]._render_py3o(
                    self.dhl_commercial_invoice.report_name,
                    res_ids=invoices.ids,
                )[0]
            ).decode("utf-8")
        else:
            return base64.b64encode(
                self.env["ir.actions.report"]._render_qweb_pdf(
                    self.dhl_commercial_invoice.report_name,
                    res_ids=invoices.ids,
                )[0]
            ).decode("utf-8")

    def _prepare_dhl_packing_data(self, picking):
        """
        Get packing data for DHL API requests
        based on the stock picking.
        """
        packages = []

        for pack in (
            picking.package_ids.filtered(lambda p: p.is_pallet) or picking.package_ids
        ):
            for _i in range(pack.package_multiplier):
                packages.append(
                    {
                        # DHL requires values to be a multiple of 0.001
                        "referenceNumber": len(packages) + 1,
                        "weight": round(pack.shipping_weight, 3),
                        "dimensions": {
                            "length": round(pack.pack_length, 3),
                            "width": round(pack.width, 3),
                            "height": round(pack.height, 3),
                        },
                    }
                )
            pack.sequence = len(packages)

        return packages

    def _get_is_customs_declarable(self, invoice):
        """
        Determine if the shipment is customs declarable.
        """
        # TODO: Burası çok karışık ve yeterli dokümantasyon sağlanmadı.
        # O yüzden şimdilik hep True döndürüyoruz.
        # return invoice.fiscal_position_id.is_export
        return True

    def _prepare_dhl_customs_data(self, picking, shipping_weight):
        """
        Prepare customs data for DHL API requests
        based on the stock picking and shipping weight.
        """
        invoice = picking.invoice_ids.filtered(lambda m: m.state == "posted")[0]
        custom_declarable = self._get_is_customs_declarable(invoice)
        data = {
            "isCustomsDeclarable": custom_declarable,
            "description": self.dhl_general_shipment_description,
            "incoterm": invoice.invoice_incoterm_id.code,
        }

        if custom_declarable:
            total_declared_value, line_items = self._prepare_dhl_custom_details_data(
                picking, shipping_weight
            )
            data["declaredValue"] = total_declared_value
            data["declaredValueCurrency"] = picking.sale_id.currency_id.name
            data["exportDeclaration"] = {
                "lineItems": line_items,
                "invoice": {
                    "number": invoice.name,
                    "date": (invoice.invoice_date or fields.Date.today()).strftime(
                        "%Y-%m-%d"
                    ),
                },
            }

        return data

    def _prepare_dhl_shipment_data(self, picking):
        """
        Prepare shipment data for DHL API requests
        based on the stock picking.
        """

        warehouse_id = picking.location_id.warehouse_id
        invoice = picking.invoice_ids.filtered(lambda m: m.state == "posted")[0]
        data = {
            "accounts": [{"typeCode": "shipper", "number": self.dhl_account_number}],
            "customerDetails": {
                "shipperDetails": {
                    "postalAddress": self._prepare_dhl_address(warehouse_id.partner_id),
                    "contactInformation": self._prepare_dhl_contact(
                        warehouse_id.partner_id
                    ),
                },
                "receiverDetails": {
                    "postalAddress": self._prepare_dhl_address(picking.partner_id),
                    "contactInformation": self._prepare_dhl_contact(picking.partner_id),
                },
            },
            "productCode": self.dhl_service_type,
            "getRateEstimates": True,
            "plannedShippingDateAndTime": self._prepare_dhl_estimated_pickup_date(),
            "pickup": {
                "isRequested": True,
                "closeTime": self.dhl_pickup_close_time,
                "location": self.dhl_pickup_location,
                "pickupDetails": {
                    "postalAddress": self._prepare_dhl_address(warehouse_id.partner_id),
                    "contactInformation": self._prepare_dhl_contact(
                        warehouse_id.partner_id
                    ),
                },
            },
            "outputImageProperties": {
                "encodingFormat": self.dhl_label_type,
                "printerDPI": int(self.dhl_label_dpi),
                "imageOptions": [
                    {
                        "typeCode": "label",
                        "templateName": "ECOM26_84_A4_001",
                    },
                    {
                        "typeCode": "waybillDoc",
                        "templateName": "ARCH_8X4_A4_002",
                        "isRequested": True,
                    },
                ],
            },
            "documentImages": [
                {
                    "typeCode": "CIN",
                    "imageFormat": "PDF",
                    "content": self._prepare_dhl_commercial_invoice_data(invoice),
                }
            ],
            "valueAddedServices": [
                {
                    "serviceCode": "WY",
                }
            ],
            "getAdditionalInformation": [
                {
                    "typeCode": "pickupDetails",
                    "isRequested": True,
                },
                {
                    "typeCode": "optionalShipmentData",
                    "isRequested": True,
                },
            ],
            "content": {
                "packages": self._prepare_dhl_packing_data(picking),
                "unitOfMeasurement": "metric",
            },
        }

        data["content"].update(
            self._prepare_dhl_customs_data(picking, picking.shipping_weight)
        )

        return data

    def dhl_rate_shipment(self, order):
        """
        Get DHL rate for the given sale order.
        """
        dhl_request = DHLRequest(
            api_key=self.dhl_api_key,
            api_secret=self.dhl_api_secret,
            prod=self.prod_environment,
            delivery_carrier=self,
        )
        payload = self._prepare_dhl_sale_rate_data(order)
        try:
            response = dhl_request.get_rate(payload)

            currency_name = response["exchangeRates"][0]["baseCurrency"]

            price = next(
                (
                    price_data["price"]
                    for price_data in response["products"][0]["totalPrice"]
                    if price_data["priceCurrency"] == currency_name
                ),
                None,
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
        except Exception as __:
            price = 0.0

        return {
            "success": True,
            "price": price,
            "error_message": False,
            "warning_message": False,
        }

    # def dhl_account_rate_shipment(self, account_move):

    def dhl_send_shipping(self, pickings):
        """
        Send DHL shipment request for the given pickings.
        """

        if self.payment_type == "customer_pays":
            raise NotImplementedError(_("DHL customer pays is not implemented yet."))

        dhl_request = DHLRequest(
            api_key=self.dhl_api_key,
            api_secret=self.dhl_api_secret,
            prod=self.prod_environment,
            delivery_carrier=self,
        )

        result = []
        for picking in pickings:
            payload = self._prepare_dhl_shipment_data(picking)
            shipment_data = dhl_request.create_shipment(payload)

            master_tracking_number = shipment_data["shipmentTrackingNumber"]

            price = shipment_data["shipmentCharges"][0]["price"]
            currency = shipment_data["shipmentCharges"][0]["priceCurrency"]

            # If needed, convert the price to the order's currency
            if currency != picking.sale_id.currency_id.name:
                currency = self.env["res.currency"].search(
                    [("name", "=", currency)], limit=1
                )

                price = currency._convert(
                    price,
                    picking.sale_id.currency_id,
                    picking.sale_id.company_id,
                    fields.Date.today(),
                )

            # We don't get the VAT from DHL API,
            # so we set it to False.
            picking.carrier_shipping_cost = price
            picking.carrier_shipping_vat = False
            picking.carrier_shipping_total = price
            picking.carrier_total_deci = shipment_data["shipmentDetails"][0][
                "volumetricWeight"
            ]
            picking.carrier_tracking_ref = master_tracking_number
            picking.shipping_number = master_tracking_number
            picking.dhl_dispatch_confirmation_number = shipment_data[
                "dispatchConfirmationNumber"
            ]

            # Save all delivery documents
            for seq, document_data in enumerate(shipment_data["documents"]):
                filename = f"dhl_label_{picking.name}_{seq}.{self.carrier_barcode_type}"

                encoded_content = document_data["content"]

                self.env["ir.attachment"].create(
                    {
                        "name": filename,
                        "datas": encoded_content,
                        "res_model": "stock.picking",
                        "res_id": picking.id,
                        "is_delivery_document": True,
                    }
                )

            picking.invoice_ids.filtered(lambda m: m.state == "posted")[0].message_post(
                body=_(
                    "DHL Pickup scheduled for <strong>%(pickup_date)s</strong>. Pickup"
                    " dispatch confirmation number: <strong>%(confirmation_number)s"
                    "</strong>.",
                    pickup_date=self._prepare_dhl_estimated_pickup_date(),
                    confirmation_number=shipment_data["dispatchConfirmationNumber"],
                )
            )

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
            api_key=self.dhl_api_key,
            api_secret=self.dhl_api_secret,
            prod=self.prod_environment,
            delivery_carrier=self,
        )

        for picking in pickings:
            if not picking.dhl_dispatch_confirmation_number:
                continue

            payload = {
                "requestorName": self.env.user.name,
                "reason": "Cancelled by user",
                "dispatchConfirmationNumber": picking.dhl_dispatch_confirmation_number,
            }

            success, error_data = dhl_request.cancel_pickup(payload)

            if not success:
                _logger.error(
                    "Failed to cancel DHL shipment for picking %s: %s",
                    picking.name,
                    error_data,
                )
                raise UserError(
                    _("Failed to cancel DHL shipment: %(data)s", data=error_data)
                )

            picking.invoice_ids[0].message_post(
                body=_("DHL pickup has been successfully cancelled.")
            )

        return True

    def clear_delivery_data(self, picking):
        res = super().clear_delivery_data(picking)

        picking.dhl_dispatch_confirmation_number = False
        picking.dhl_tracking_url = False

        return res

    def dhl_tracking_state_update(self, picking):
        """Tracking state update"""
        self.ensure_one()
        if not picking.carrier_tracking_ref:
            return

        dhl_request = DHLRequest(
            api_key=self.dhl_api_key,
            api_secret=self.dhl_api_secret,
            prod=self.prod_environment,
            delivery_carrier=self,
        )

        payload = {
            "shipmentTrackingNumber": picking.carrier_tracking_ref,
            "trackingView": "shipment-details-only",
            "levelOfDetail": "shipment",
            "requestControlledAccessDataCodes": True,
        }

        response = dhl_request.tracking_state_update(payload)

        shipment = response["shipments"][0]

        # Build tracking event history
        events = shipment.get("events", [])
        tracking_history_lines = []

        for event in events:
            event_date = event.get("date", "")
            event_time = event.get("time", "")
            event_description = event.get("description", "")
            event_code = event.get("typeCode", "")

            # Truncate the description if it's too long
            # to avoid cluttering the history.
            if len(event_description) > 65:
                event_description = event_description[:65] + "..."

            tracking_history_lines.append(
                f"{event_time} {event_date} - [{event_code}] {event_description}"
            )

        # Save tracking history
        picking.tracking_state_history = "\n".join(tracking_history_lines)

        last_event = events[-1] if events else None

        if last_event:
            picking.delivery_state = DHL_STATUS_CODE_MAP.get(
                last_event.get("typeCode"), "in_transit"
            )
            if last_event.get("typeCode") == "OK":
                # GMT offset is optional
                dd_local = datetime.fromisoformat(
                    f"{last_event['date']}T{last_event['time']}"
                    f"{last_event.get('GMTOffset', '')}"
                )

                picking.date_delivered = dd_local.astimezone(pytz.UTC).replace(
                    tzinfo=None
                )

        return True

    def get_tracking_link(self, picking):
        if picking.carrier_id.delivery_type == "dhl":
            return picking.dhl_tracking_url

        return super().get_tracking_link(picking)
