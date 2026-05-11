# Copyright 2026 Altinkaya Enclosures, Ahmet Yigit Budak
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import base64
import logging
import re
import textwrap
from datetime import datetime, timedelta
from io import BytesIO

import phonenumbers
import pytz
from PIL import Image

from odoo import _, fields, models
from odoo.exceptions import UserError

from .ups_request import UPSRequest

# Strips a leading "[SKU]" prefix Altinkaya prepends to product display names.
# UPS InternationalForms.Description is capped at 35 chars, and the bracketed
# code burns ~16 chars while telling customs nothing useful.
PRODUCT_NAME_SKU_PREFIX_RE = re.compile(r"^\[[^\]]+\]\s*")

UPS_SERVICES = [
    ("01", "Next Day Air"),
    ("02", "2nd Day Air"),
    ("03", "Ground"),
    ("07", "Worldwide Express"),
    ("08", "Worldwide Expedited"),
    ("11", "UPS Standard"),
    ("12", "3 Day Select"),
    ("13", "Next Day Air Saver"),
    ("14", "Next Day Air Early"),
    ("17", "Worldwide Economy DDU"),
    ("54", "Worldwide Express Plus"),
    ("65", "UPS Saver"),
    ("72", "Worldwide Economy DDP"),
    ("74", "UPS Express 12:00"),
]

UPS_PACKAGING_CODES = [
    ("02", "Customer Supplied Package"),
    ("2a", "Small Express Box"),
    ("2b", "Medium Express Box"),
    ("2c", "Large Express Box"),
    ("24", "25KG Box"),
    ("25", "10KG Box"),
    ("30", "Pallet"),
]

UPS_PAYMENT_TYPES = [
    ("SENDER", "Sender"),
    ("RECEIVER", "Receiver"),
    ("THIRD_PARTY", "Third Party"),
]

UPS_PICKUP_TYPES = [
    ("01", "Daily Pickup"),
    ("03", "Customer Counter"),
    ("06", "One Time Pickup"),
    ("07", "On Call Air"),
    ("19", "Letter Center"),
    ("20", "Air Service Center"),
]

UPS_REASON_FOR_EXPORT = [
    ("SALE", "Sale"),
    ("GIFT", "Gift"),
    ("SAMPLE", "Sample"),
    ("RETURN", "Return"),
    ("REPAIR", "Repair"),
    ("INTERCOMPANYDATA", "Intercompany Data"),
]

UPS_LABEL_CHARACTER_SET = [
    ("dos", "DOS/ASCII"),
    ("tur", "Turkish (Latin-5)"),
]

# Map UPS currentStatus.type codes to Odoo delivery_state values.
# Per UPS Tracking.yaml: P=Pickup, M=Manifest, I=InTransit, D=Delivered, X=Exception.
UPS_TO_ODOO_STATUS = {
    "M": "shipping_recorded_in_carrier",
    "P": "shipping_recorded_in_carrier",
    "I": "in_transit",
    "D": "customer_delivered",
    "X": "incident",
}

_logger = logging.getLogger(__name__)


class DeliveryCarrier(models.Model):
    _inherit = "delivery.carrier"

    delivery_type = fields.Selection(
        selection_add=[("ups", "UPS")],
        ondelete={"ups": "set default"},
    )

    ups_client_id = fields.Char(string="UPS Client ID", help="UPS OAuth Client ID")
    ups_client_secret = fields.Char(help="UPS OAuth Client Secret")
    ups_account_number = fields.Char(
        help="UPS 6-character account number (a.k.a. Shipper Number)."
    )
    ups_service_type = fields.Selection(selection=UPS_SERVICES)
    ups_packaging_type = fields.Selection(
        selection=UPS_PACKAGING_CODES,
        default="02",
        help="Default packaging code when no pallets are present.",
    )
    ups_pickup_type = fields.Selection(
        selection=UPS_PICKUP_TYPES,
        default="01",
        help="Pickup behaviour. '01 Daily Pickup' means UPS collects at"
        " the scheduled daily time and no explicit pickup call is needed.",
    )
    ups_customs_payment_type = fields.Selection(
        selection=UPS_PAYMENT_TYPES,
        default="SENDER",
    )
    ups_negotiated_rates = fields.Boolean(
        default=True,
        help="Request UPS account negotiated rates in addition to published rates.",
    )
    ups_label_character_set = fields.Selection(
        selection=UPS_LABEL_CHARACTER_SET,
        default="tur",
        help="Label character set. 'tur' (Latin-5) preserves Turkish characters"
        " natively so no ASCII normalization is required.",
    )
    ups_commercial_invoice = fields.Many2one(
        "ir.actions.report",
        string="UPS Commercial Invoice",
        help="Commercial invoice report used to render customs documentation."
        " Only used if UPS does not render the invoice from InternationalForms.",
    )
    ups_reason_for_export = fields.Selection(
        selection=UPS_REASON_FOR_EXPORT,
        default="SALE",
    )
    ups_label_stock_size_height = fields.Integer(
        default=6, help="ZPL label height in inches (UPS allows 6 or 8)."
    )
    ups_label_stock_size_width = fields.Integer(
        default=4, help="ZPL label width in inches (UPS uses 4)."
    )

    # ---------------------------------------------------------------------
    # Payload builders
    # ---------------------------------------------------------------------
    def _get_estimated_weight_from_order_line(self, order_line):
        return order_line.product_id.weight * order_line.qty_to_deliver

    def _get_package_count(self, packages):
        """Return total package count considering package_multiplier."""
        return sum(p.package_multiplier for p in packages)

    def _split_ups_address_lines(self, partner, max_len=35, max_lines=3):
        """Split partner street/street2 into UPS-compliant AddressLine entries.

        UPS allows up to 3 lines, each ≤ 35 chars. Lines that fit are kept
        as-is; longer lines are wrapped at word boundaries.
        """
        result = []
        for line in [partner.street, partner.street2]:
            if not line:
                continue
            if len(line) <= max_len:
                result.append(line)
            else:
                result.extend(textwrap.wrap(line, width=max_len, break_long_words=True))
            if len(result) >= max_lines:
                break
        result = [chunk[:max_len] for chunk in result[:max_lines]]
        return result or [""]

    def _prepare_ups_address(self, partner):
        """Build a UPS Address dict for a partner."""
        address = {
            "AddressLine": self._split_ups_address_lines(partner),
            "City": partner.city or (partner.state_id.name if partner.state_id else ""),
            "PostalCode": partner.zip or "",
            "CountryCode": partner.country_id.code or "",
        }
        if partner.state_id and partner.state_id.code:
            address["StateProvinceCode"] = partner.state_id.code
        return address

    def _format_phone(self, partner):
        """Return phone digits in UPS-friendly format, or empty string."""
        raw = partner.phone or partner.mobile
        if not raw:
            return ""
        try:
            parsed = phonenumbers.parse(raw, partner.country_id.code or None)
            formatted = phonenumbers.format_number(
                parsed, phonenumbers.PhoneNumberFormat.E164
            )
            # UPS wants just digits; drop leading '+'.
            return formatted.lstrip("+")
        except phonenumbers.NumberParseException:
            return "".join(ch for ch in raw if ch.isdigit())

    def _prepare_ups_contact(self, partner):
        """Build a UPS contact payload (Name/AttentionName/Phone/EMail)."""
        commercial = partner.commercial_partner_id
        contact = {
            "Name": (commercial.name or partner.name or "")[:35],
            "AttentionName": (partner.name or commercial.name or "")[:35],
        }
        phone = self._format_phone(partner)
        if phone:
            contact["Phone"] = {"Number": phone}
        if partner.email:
            contact["EMailAddress"] = partner.email
        return contact

    def _prepare_ups_shipper_block(self, partner):
        """Shipper block is a Contact + Address + ShipperNumber + optional tax id."""
        data = self._prepare_ups_contact(partner)
        data["ShipperNumber"] = self.ups_account_number or ""
        data["Address"] = self._prepare_ups_address(partner)
        if partner.vat:
            data["TaxIdentificationNumber"] = partner.vat
        return data

    def _prepare_ups_party_block(self, partner):
        """Generic party block (ShipTo / ShipFrom)."""
        data = self._prepare_ups_contact(partner)
        data["Address"] = self._prepare_ups_address(partner)
        if partner.vat:
            data["TaxIdentificationNumber"] = partner.vat
        return data

    def _prepare_ups_dummy_packages(self, order):
        """Build UPS Package entries from dummy packages (used for rating)."""
        if order.picking_ids:
            raise UserError(_("Cannot get rates for an order with existing pickings."))

        raw_packages = self._generate_dummy_packages(order.sale_deci)
        packages = []
        for pack in raw_packages:
            dims = pack.get("dimensions", {})
            packages.append(
                {
                    "Packaging": {
                        "Code": "30"
                        if pack.get("is_pallet")
                        else self.ups_packaging_type
                    },
                    "Dimensions": {
                        "UnitOfMeasurement": {"Code": "CM"},
                        "Length": str(round(dims.get("length", 0.0), 2)),
                        "Width": str(round(dims.get("width", 0.0), 2)),
                        "Height": str(round(dims.get("height", 0.0), 2)),
                    },
                    "PackageWeight": {
                        "UnitOfMeasurement": {"Code": "KGS"},
                        "Weight": str(round(pack.get("weight", 0.1), 2)),
                    },
                }
            )
        return packages

    def _prepare_ups_real_packages(self, picking):
        """Build UPS Package entries from the actual picking packages.

        Returns (packages, total_weight). Honours pallet multipliers and sets
        each stock.quant.package sequence so the saved label order matches.
        """
        packages = []
        total_weight = 0.0
        pallets = picking.package_ids.filtered(lambda p: p.is_pallet)
        source = pallets or picking.package_ids

        for pack in source:
            packaging_code = "30" if pack.is_pallet else self.ups_packaging_type
            for _i in range(pack.package_multiplier):
                packages.append(
                    {
                        "Packaging": {"Code": packaging_code},
                        "Dimensions": {
                            "UnitOfMeasurement": {
                                "Code": (pack.length_uom_id.name or "CM").upper()
                            },
                            "Length": str(round(pack.pack_length or 0.0, 2)),
                            "Width": str(round(pack.width or 0.0, 2)),
                            "Height": str(round(pack.height or 0.0, 2)),
                        },
                        "PackageWeight": {
                            "UnitOfMeasurement": {"Code": "KGS"},
                            "Weight": str(round(pack.shipping_weight or 0.1, 2)),
                        },
                    }
                )
                total_weight += pack.shipping_weight or 0.0
            pack.sequence = len(packages)

        return packages, total_weight

    def _prepare_ups_payment_info(self, picking):
        """PaymentInformation block for shipping charges (Type=01 Transportation)."""
        bill_shipper = {
            "Type": "01",
            "BillShipper": {"AccountNumber": self.ups_account_number or ""},
        }
        if self.payment_type == "sender_pays":
            return {"ShipmentCharge": bill_shipper}

        # customer_pays — bill receiver using their UPS account if available
        # (falls back to bill shipper when partner has no UPS account).
        receiver_account = picking.partner_id.commercial_partner_id.vat or ""
        bill_receiver = {
            "Type": "01",
            "BillReceiver": {
                "AccountNumber": receiver_account,
                "Address": {
                    "PostalCode": picking.partner_id.zip or "",
                },
            },
        }
        return {"ShipmentCharge": bill_receiver if receiver_account else bill_shipper}

    def _prepare_ups_international_forms(self, picking, total_weight):
        """Build the InternationalForms block for cross-border shipments.

        Only called when shipper country != recipient country. Returns None
        if no posted invoice is available (caller decides how to handle).
        """
        invoice = picking.invoice_ids.filtered(lambda m: m.state == "posted")[:1]
        if not invoice:
            return None

        lines_to_ship = invoice.invoice_line_ids.filtered(
            lambda l: not (l.product_id.default_code or "").startswith("KAR-PO")
        )
        if not lines_to_ship:
            return None

        avg_line_weight = total_weight / len(lines_to_ship) if total_weight else 0.1
        currency_code = invoice.currency_id.name

        products = []
        for line in lines_to_ship:
            hs_code = line.product_id.categ_id.hs_code_id or line.product_id.hs_code_id
            description = (
                hs_code.with_context(lang="en_US").description
                if hs_code
                else line.product_id.with_context(lang="en_US").name
            )
            description = description or line.product_id.name or "Goods"
            description = PRODUCT_NAME_SKU_PREFIX_RE.sub("", description)[:35]
            unit_price = max(round(line.price_unit or 0.0, 3), 0.01)
            products.append(
                {
                    "Description": description,
                    "CommodityCode": hs_code.hs_code if hs_code else "",
                    "OriginCountryCode": (
                        line.product_id.country_of_origin.code or "TR"
                    ),
                    "Unit": {
                        "Number": str(int(max(line.quantity or 1.0, 1.0))),
                        "Value": str(unit_price),
                        "UnitOfMeasurement": {"Code": "PCS"},
                    },
                    "ProductWeight": {
                        "UnitOfMeasurement": {"Code": "KGS"},
                        "Weight": str(round(max(avg_line_weight, 0.1), 2)),
                    },
                }
            )

        forms = {
            "FormType": ["01"],
            "InvoiceNumber": invoice.name,
            "InvoiceDate": (invoice.invoice_date or fields.Date.today()).strftime(
                "%Y%m%d"
            ),
            "ReasonForExport": self.ups_reason_for_export,
            "CurrencyCode": currency_code,
            # UPS docs are ambiguous — the schema says Contacts is for EEI/USMCA
            # only, but the official FormType=01 sample includes SoldTo, and
            # Paperless Invoice flows reject the request with 9120800 without it.
            "Contacts": {"SoldTo": self._prepare_ups_party_block(picking.partner_id)},
            "Product": products,
        }
        if invoice.invoice_incoterm_id:
            forms["TermsOfShipment"] = invoice.invoice_incoterm_id.code
        return forms

    def _prepare_ups_base_rate_data(self, warehouse_partner, recipient_partner):
        return {
            "RateRequest": {
                "Request": {
                    "TransactionReference": {"CustomerContext": "Altinkaya Odoo Rating"}
                },
                "Shipment": {
                    "Shipper": self._prepare_ups_shipper_block(warehouse_partner),
                    "ShipTo": self._prepare_ups_party_block(recipient_partner),
                    "ShipFrom": self._prepare_ups_party_block(warehouse_partner),
                    "PaymentDetails": {
                        "ShipmentCharge": [
                            {
                                "Type": "01",
                                "BillShipper": {
                                    "AccountNumber": self.ups_account_number or "",
                                },
                            }
                        ]
                    },
                    "Service": {
                        "Code": self.ups_service_type or "11",
                    },
                },
            }
        }

    def _prepare_ups_sale_rate_data(self, order):
        data = self._prepare_ups_base_rate_data(
            order.warehouse_id.partner_id, order.partner_shipping_id
        )
        shipment = data["RateRequest"]["Shipment"]
        shipment["Package"] = self._prepare_ups_dummy_packages(order)
        shipment["NumOfPieces"] = str(len(shipment["Package"]))
        if self.ups_negotiated_rates:
            shipment["ShipmentRatingOptions"] = {"NegotiatedRatesIndicator": "Y"}
        return data

    def _prepare_ups_shipment_data(self, picking):
        warehouse_partner = picking.location_id.warehouse_id.partner_id
        recipient = picking.partner_id

        packages, total_weight = self._prepare_ups_real_packages(picking)

        label_image_code = "ZPL" if self.carrier_barcode_type == "zpl" else "GIF"
        label_spec = {
            "LabelImageFormat": {"Code": label_image_code},
        }
        if label_image_code == "GIF":
            label_spec["HTTPUserAgent"] = "Mozilla/5.0"
        else:
            label_spec["LabelStockSize"] = {
                "Height": str(self.ups_label_stock_size_height or 6),
                "Width": str(self.ups_label_stock_size_width or 4),
            }
        if self.ups_label_character_set:
            label_spec["CharacterSet"] = self.ups_label_character_set

        shipment = {
            "Description": (picking.sale_id.name if picking.sale_id else picking.name)[
                :50
            ],
            "Shipper": self._prepare_ups_shipper_block(warehouse_partner),
            "ShipTo": self._prepare_ups_party_block(recipient),
            "ShipFrom": self._prepare_ups_party_block(warehouse_partner),
            "PaymentInformation": self._prepare_ups_payment_info(picking),
            "Service": {"Code": self.ups_service_type or "11"},
            "Package": packages,
        }
        if self.ups_negotiated_rates:
            shipment["ShipmentRatingOptions"] = {"NegotiatedRatesIndicator": "Y"}

        # Cross-border: add customs / InternationalForms.
        shipper_country = warehouse_partner.country_id.code or "TR"
        recipient_country = recipient.country_id.code or ""
        if shipper_country != recipient_country:
            forms = self._prepare_ups_international_forms(picking, total_weight)
            if forms:
                shipment["ShipmentServiceOptions"] = {"InternationalForms": forms}

        return {
            "ShipmentRequest": {
                "Request": {
                    "RequestOption": "nonvalidate",
                    "TransactionReference": {"CustomerContext": picking.name},
                },
                "Shipment": shipment,
                "LabelSpecification": label_spec,
            }
        }

    # ---------------------------------------------------------------------
    # Response formatters
    # ---------------------------------------------------------------------
    def _format_ups_rate_data(self, response):
        """Return {'price', 'currency'} from a RateResponse, preferring negotiated."""
        try:
            rated = response["RateResponse"]["RatedShipment"]
        except (KeyError, TypeError) as exc:
            raise UserError(_("UPS rate response missing RatedShipment data.")) from exc

        if isinstance(rated, list):
            rated = rated[0]

        negotiated = rated.get("NegotiatedRateCharges", {}).get("TotalCharge")
        if negotiated:
            return {
                "price": float(negotiated.get("MonetaryValue") or 0.0),
                "currency": negotiated.get("CurrencyCode") or "",
            }
        total = rated.get("TotalCharges", {})
        return {
            "price": float(total.get("MonetaryValue") or 0.0),
            "currency": total.get("CurrencyCode") or "",
        }

    def _format_shipment_rate(self, shipment_results):
        """Return {'price', 'currency', 'billing_weight'} from ShipmentResults."""
        negotiated = shipment_results.get("NegotiatedRateCharges", {}).get(
            "TotalCharge"
        )
        if negotiated:
            price = float(negotiated.get("MonetaryValue") or 0.0)
            currency = negotiated.get("CurrencyCode") or ""
        else:
            charges = shipment_results.get("ShipmentCharges", {}).get(
                "TotalCharges", {}
            )
            price = float(charges.get("MonetaryValue") or 0.0)
            currency = charges.get("CurrencyCode") or ""

        billing_weight = float(
            (shipment_results.get("BillingWeight", {}) or {}).get("Weight") or 0.0
        )
        return {"price": price, "currency": currency, "billing_weight": billing_weight}

    # ---------------------------------------------------------------------
    # Validation
    # ---------------------------------------------------------------------
    def _validate_ups_shipping_data(self, picking):
        errors = []
        warehouse_partner = picking.location_id.warehouse_id.partner_id
        recipient = picking.partner_id

        for partner, label in [
            (warehouse_partner, _("Shipper")),
            (recipient, _("Recipient")),
        ]:
            if not partner.street:
                errors.append(
                    _(
                        "- %(type)s (%(name)s): Street address is required.",
                        type=label,
                        name=partner.display_name,
                    )
                )
            if not partner.city and not partner.state_id:
                errors.append(
                    _(
                        "- %(type)s (%(name)s): City or State is required.",
                        type=label,
                        name=partner.display_name,
                    )
                )
            if not partner.zip:
                errors.append(
                    _(
                        "- %(type)s (%(name)s): ZIP/Postal code is required.",
                        type=label,
                        name=partner.display_name,
                    )
                )
            if not partner.country_id:
                errors.append(
                    _(
                        "- %(type)s (%(name)s): Country is required.",
                        type=label,
                        name=partner.display_name,
                    )
                )
            if not partner.phone and not partner.mobile:
                errors.append(
                    _(
                        "- %(type)s (%(name)s): Phone or Mobile number is required.",
                        type=label,
                        name=partner.display_name,
                    )
                )

        if not picking.package_ids:
            errors.append(
                _(
                    "- Picking %(name)s: At least one package is required.",
                    name=picking.name,
                )
            )
        else:
            for package in picking.package_ids:
                if not package.shipping_weight or package.shipping_weight <= 0:
                    errors.append(
                        _(
                            "- Package %(package)s: Weight must be greater than 0.",
                            package=package.name,
                        )
                    )
                if not package.pack_length or package.pack_length <= 0:
                    errors.append(
                        _(
                            "- Package %(package)s: Length must be greater than 0.",
                            package=package.name,
                        )
                    )
                if not package.width or package.width <= 0:
                    errors.append(
                        _(
                            "- Package %(package)s: Width must be greater than 0.",
                            package=package.name,
                        )
                    )
                if not package.height or package.height <= 0:
                    errors.append(
                        _(
                            "- Package %(package)s: Height must be greater than 0.",
                            package=package.name,
                        )
                    )

        shipper_country = warehouse_partner.country_id.code or "TR"
        recipient_country = recipient.country_id.code or ""
        if shipper_country != recipient_country and not picking.invoice_ids.filtered(
            lambda m: m.state == "posted"
        ):
            errors.append(
                _(
                    "- Picking %(name)s: A posted invoice is required for UPS"
                    " international shipments (needed for customs).",
                    name=picking.name,
                )
            )

        if errors:
            raise UserError(
                _(
                    "Cannot send UPS shipment. Please fix the following issues:\n\n"
                    "%(errors)s",
                    errors="\n".join(errors),
                )
            )

    # ---------------------------------------------------------------------
    # Carrier entry points (dispatched by delivery.carrier by delivery_type)
    # ---------------------------------------------------------------------
    def ups_rate_shipment(self, order):
        """Return {success, price, error_message, warning_message} for a sale order."""
        price = 0.0
        try:
            ups_request = UPSRequest(
                prod=self.prod_environment,
                client_id=self.ups_client_id,
                client_secret=self.ups_client_secret,
                account_number=self.ups_account_number,
                delivery_carrier=self,
            )
            payload = self._prepare_ups_sale_rate_data(order)
            response = ups_request.get_rate(payload)

            rate_data = self._format_ups_rate_data(response)
            price = rate_data["price"]
            currency_code = rate_data["currency"]

            if currency_code and currency_code != order.currency_id.name:
                currency = self.env["res.currency"].search(
                    [("name", "=", currency_code)], limit=1
                )
                if currency:
                    price = currency._convert(
                        price,
                        order.currency_id,
                        order.company_id,
                        fields.Date.today(),
                    )
        except Exception as exc:
            _logger.error("UPS rate_shipment failed: %s", exc, exc_info=True)
            price = 0.0

        return {
            "success": True,
            "price": price,
            "error_message": False,
            "warning_message": False,
        }

    def _ups_label_gif_to_pdf(self, gif_b64):
        """Convert a UPS GIF label (base64) to a portrait PDF (base64).

        UPS Shipping API returns labels in landscape; we rotate 90° clockwise
        to portrait, scale to 80% and center on a white page of the original
        rotated dimensions so there's a uniform margin around the label.
        """
        img = Image.open(BytesIO(base64.b64decode(gif_b64)))
        if img.mode != "RGB":
            img = img.convert("RGB")
        img = img.rotate(-90, expand=True)

        page_w, page_h = img.size
        scaled = img.resize((int(page_w * 0.8), int(page_h * 0.8)), Image.LANCZOS)
        canvas = Image.new("RGB", (page_w, page_h), "white")
        canvas.paste(
            scaled,
            ((page_w - scaled.width) // 2, (page_h - scaled.height) // 2),
        )

        pdf_buf = BytesIO()
        canvas.save(pdf_buf, format="PDF", resolution=203.0)
        return base64.b64encode(pdf_buf.getvalue()).decode("ascii")

    def ups_send_shipping(self, pickings):
        """Create UPS shipments and return [{exact_price, tracking_number}, ...]."""
        for picking in pickings:
            self._validate_ups_shipping_data(picking)

        ups_request = UPSRequest(
            prod=self.prod_environment,
            client_id=self.ups_client_id,
            client_secret=self.ups_client_secret,
            account_number=self.ups_account_number,
            delivery_carrier=self,
        )

        result = []
        for picking in pickings:
            payload = self._prepare_ups_shipment_data(picking)
            response = ups_request.create_shipment(payload)

            shipment_results = response["ShipmentResponse"]["ShipmentResults"]
            master_tracking = shipment_results["ShipmentIdentificationNumber"]
            package_results = shipment_results.get("PackageResults") or []
            if isinstance(package_results, dict):
                package_results = [package_results]

            per_package_numbers = [
                pr.get("TrackingNumber")
                for pr in package_results
                if pr.get("TrackingNumber")
            ]
            picking.multiple_shipping_numbers = (
                ", ".join(per_package_numbers) if len(per_package_numbers) > 1 else ""
            )

            rate_info = self._format_shipment_rate(shipment_results)
            price = rate_info["price"]
            currency_code = rate_info["currency"]

            # Store costs on picking (convert to picking/order currency if needed).
            picking.carrier_shipping_cost = price
            picking.carrier_shipping_vat = False
            picking.carrier_shipping_total = price
            picking.carrier_total_deci = rate_info["billing_weight"]
            picking.carrier_tracking_ref = master_tracking
            picking.shipping_number = master_tracking

            # Save labels as ir.attachment (one per package). UPS Shipping API
            # only returns GIF or ZPL — never PDF directly. For non-ZPL output
            # we wrap the GIF in a portrait-oriented PDF locally.
            is_zpl = self.carrier_barcode_type == "zpl"
            label_ext = "zpl" if is_zpl else "pdf"
            label_mimetype = "text/plain" if is_zpl else "application/pdf"
            for seq, pr in enumerate(package_results):
                label = (pr.get("ShippingLabel") or {}).get("GraphicImage")
                if not label:
                    continue
                data = label if is_zpl else self._ups_label_gif_to_pdf(label)
                self.env["ir.attachment"].create(
                    {
                        "name": f"ups_label_{picking.name}_{seq}.{label_ext}",
                        "datas": data,
                        "mimetype": label_mimetype,
                        "res_model": "stock.picking",
                        "res_id": picking.id,
                        "is_delivery_document": True,
                    }
                )

            # Chatter notification on the posted invoice (if present).
            posted_invoice = picking.invoice_ids.filtered(
                lambda m: m.state == "posted"
            )[:1]
            if posted_invoice:
                posted_invoice.message_post(
                    body=_(
                        "UPS shipment created. Tracking number:"
                        " <strong>%(tracking)s</strong>.",
                        tracking=master_tracking,
                    )
                )

            # Non-daily pickup types need an explicit pickup request. We treat
            # Daily Pickup (01) as "no call needed" — UPS collects at the
            # scheduled daily time.
            if self.ups_pickup_type and self.ups_pickup_type != "01":
                try:
                    self._ups_request_pickup(
                        picking, master_tracking, rate_info["billing_weight"]
                    )
                except Exception as exc:
                    _logger.error(
                        "UPS pickup request failed for picking %s: %s",
                        picking.name,
                        exc,
                    )

            # Convert price into picking's currency for uniform reporting.
            if (
                currency_code
                and picking.sale_id
                and currency_code != picking.sale_id.currency_id.name
            ):
                currency = self.env["res.currency"].search(
                    [("name", "=", currency_code)], limit=1
                )
                if currency:
                    price = currency._convert(
                        price,
                        picking.sale_id.currency_id,
                        picking.sale_id.company_id,
                        fields.Date.today(),
                    )
                    picking.carrier_shipping_cost = price
                    picking.carrier_shipping_total = price

            result.append({"exact_price": price, "tracking_number": master_tracking})

        return result

    def ups_cancel_shipment(self, pickings):
        """Void UPS shipments for the given pickings."""
        ups_request = UPSRequest(
            prod=self.prod_environment,
            client_id=self.ups_client_id,
            client_secret=self.ups_client_secret,
            account_number=self.ups_account_number,
            delivery_carrier=self,
        )

        res = True
        for picking in pickings.filtered("carrier_tracking_ref"):
            if picking.delivery_state != "shipping_recorded_in_carrier":
                _logger.warning(
                    "Cannot cancel UPS shipment for picking %s (state=%s).",
                    picking.name,
                    picking.delivery_state,
                )
                continue

            response = ups_request.cancel_shipment(picking.carrier_tracking_ref)
            status_code = (
                response.get("VoidShipmentResponse", {})
                .get("SummaryResult", {})
                .get("Status", {})
                .get("Code")
            )
            success = status_code == "1"
            if success:
                # Cancel an associated pickup if we scheduled one.
                if picking.ups_pickup_prn:
                    try:
                        ups_request.cancel_pickup(picking.ups_pickup_prn)
                    except Exception as exc:
                        _logger.error(
                            "UPS pickup cancel failed for picking %s: %s",
                            picking.name,
                            exc,
                        )
            res = res and success

        return res

    def ups_tracking_state_update(self, picking):
        """Refresh delivery_state, tracking history, and date_delivered."""
        self.ensure_one()
        if not picking.carrier_tracking_ref:
            return True

        ups_request = UPSRequest(
            prod=self.prod_environment,
            client_id=self.ups_client_id,
            client_secret=self.ups_client_secret,
            account_number=self.ups_account_number,
            delivery_carrier=self,
        )

        response = ups_request.tracking_state_update(picking.carrier_tracking_ref)
        try:
            shipment = response["trackResponse"]["shipment"][0]
            package = shipment["package"][0]
        except (KeyError, IndexError, TypeError):
            _logger.warning(
                "UPS tracking response for %s missing shipment/package data.",
                picking.carrier_tracking_ref,
            )
            return True

        current_status = package.get("currentStatus", {})
        picking.delivery_state = UPS_TO_ODOO_STATUS.get(
            current_status.get("type"), "shipping_recorded_in_carrier"
        )

        activities = package.get("activity", []) or []
        # UPS returns activity newest-first; flip to chronological for history.
        history_lines = []
        for activity in reversed(activities):
            status = activity.get("status", {}) or {}
            date = activity.get("date", "")
            time = activity.get("time", "")
            history_lines.append(
                _(
                    "%(time)s %(date)s - [%(code)s] %(description)s",
                    time=time,
                    date=date,
                    code=status.get("code", ""),
                    description=status.get("description", ""),
                )
            )
        picking.tracking_state_history = "\n".join(history_lines)

        delivery_info = package.get("deliveryInformation") or {}
        if delivery_info.get("receivedBy"):
            picking.carrier_received_by = delivery_info["receivedBy"]

        delivered_entry = next(
            (
                d
                for d in (package.get("deliveryDate") or [])
                if d.get("type") == "DEL" and d.get("date")
            ),
            None,
        )
        if delivered_entry:
            try:
                picking.date_delivered = datetime.strptime(
                    delivered_entry["date"], "%Y%m%d"
                )
            except ValueError as exc:
                _logger.warning(
                    "UPS tracking: could not parse delivered date %r: %s",
                    delivered_entry.get("date"),
                    exc,
                )

        return True

    def _get_ups_pickup_service_code(self):
        """Pickup ServiceCode is 3 chars; shipping ups_service_type is 2 chars.
        UPS maps them by zero-padding (e.g. shipment "11" → pickup "011").
        """
        if not self.ups_service_type:
            return "011"
        return self.ups_service_type.zfill(3)

    def _get_ups_pickup_window(self, cutoff_hour=15):
        """Pick a (pickup_date, ready_time, close_time) in local time.

        UPS rejects pickups when CloseTime - ReadyTime is below the lead time,
        and rolls ReadyTime forward when it is earlier than 'now'. To stay
        safely above the lead time we defer the pickup to the next business
        day once the local time has crossed the cutoff hour.
        """
        tz = pytz.timezone(self.env.user.tz or "Europe/Istanbul")
        now_local = pytz.utc.localize(fields.Datetime.now()).astimezone(tz)

        if now_local.hour >= cutoff_hour or not self._is_tr_business_day(now_local):
            pickup_dt = self._get_next_tr_business_day(now_local + timedelta(days=1))
            ready_time = "0900"
        else:
            pickup_dt = now_local
            # Pad 30 min so UPS does not overlap with the current minute.
            ready_dt = now_local + timedelta(minutes=30)
            ready_time = ready_dt.strftime("%H%M")

        return pickup_dt.strftime("%Y%m%d"), ready_time, "1700"

    def _ups_request_pickup(self, picking, tracking_number, total_weight):
        """Schedule a UPS pickup for non-daily pickup types."""
        self.ensure_one()
        warehouse_partner = picking.location_id.warehouse_id.partner_id

        pickup_date, ready_time, close_time = self._get_ups_pickup_window()
        address_lines = self._split_ups_address_lines(warehouse_partner)

        payload = {
            "PickupCreationRequest": {
                "Request": {
                    "TransactionReference": {"CustomerContext": picking.name or ""},
                },
                "RatePickupIndicator": "N",
                "Shipper": {
                    "Account": {
                        "AccountNumber": self.ups_account_number or "",
                        "AccountCountryCode": (
                            warehouse_partner.country_id.code
                            or self.env.company.country_id.code
                            or "TR"
                        ),
                    }
                },
                "PickupDateInfo": {
                    "CloseTime": close_time,
                    "ReadyTime": ready_time,
                    "PickupDate": pickup_date,
                },
                "PickupAddress": {
                    "CompanyName": (warehouse_partner.commercial_partner_id.name or "")[
                        :27
                    ],
                    "ContactName": (warehouse_partner.name or "")[:22],
                    "AddressLine": address_lines,
                    "City": warehouse_partner.city or "",
                    "StateProvince": (
                        warehouse_partner.state_id.code
                        or warehouse_partner.state_id.name
                        or ""
                    ),
                    "PostalCode": warehouse_partner.zip or "",
                    "CountryCode": warehouse_partner.country_id.code or "",
                    "ResidentialIndicator": "N",
                    "Phone": {"Number": self._format_phone(warehouse_partner)},
                },
                "AlternateAddressIndicator": "N",
                "PickupPiece": [
                    {
                        "ServiceCode": self._get_ups_pickup_service_code(),
                        "Quantity": str(self._get_package_count(picking.package_ids)),
                        "DestinationCountryCode": (
                            picking.partner_id.country_id.code or ""
                        ),
                        "ContainerCode": "01",
                    }
                ],
                "TotalWeight": {
                    "Weight": "%.1f" % (total_weight or 0.1),
                    "UnitOfMeasurement": "KGS",
                },
                "OverweightIndicator": "Y" if (total_weight or 0) > 32 else "N",
                "TrackingData": [{"TrackingNumber": tracking_number}],
                "PaymentMethod": "01",
                "ReferenceNumber": picking.name or "",
            }
        }

        ups_request = UPSRequest(
            prod=self.prod_environment,
            client_id=self.ups_client_id,
            client_secret=self.ups_client_secret,
            account_number=self.ups_account_number,
            delivery_carrier=self,
        )
        response = ups_request.request_pickup(payload)

        prn = (response.get("PickupCreationResponse") or {}).get("PRN")
        if prn:
            picking.ups_pickup_prn = prn
            picking.ups_pickup_date = datetime.strptime(pickup_date, "%Y%m%d")
            posted_invoice = picking.invoice_ids.filtered(
                lambda m: m.state == "posted"
            )[:1]
            if posted_invoice:
                posted_invoice.message_post(
                    body=_(
                        "UPS pickup scheduled for <strong>%(date)s</strong>."
                        " PRN: <strong>%(prn)s</strong>.",
                        date=pickup_date,
                        prn=prn,
                    )
                )
        return True

    # ---------------------------------------------------------------------
    # Overrides
    # ---------------------------------------------------------------------
    def clear_delivery_data(self, picking):
        res = super().clear_delivery_data(picking)
        picking.ups_pickup_prn = False
        picking.ups_pickup_date = False
        return res

    def get_tracking_link(self, picking):
        if picking.carrier_id.delivery_type == "ups" and picking.carrier_tracking_ref:
            url = (
                "https://www.ups.com/track?loc=en_US&tracknum="
                + picking.carrier_tracking_ref
            )
            shortener = self.url_shortener_id
            if shortener:
                existing = shortener.shortened_urls.search(
                    [
                        ("long_url", "=", url),
                        ("id", "in", shortener.shortened_urls.ids),
                    ],
                    limit=1,
                ).short_url
                return existing or shortener.shorten_url(url)
            return url
        return super().get_tracking_link(picking)
