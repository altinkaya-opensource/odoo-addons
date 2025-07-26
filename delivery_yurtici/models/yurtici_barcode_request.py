# Copyright 2025 Altinkaya Open Source
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

import logging
from xml.etree import ElementTree as ET

from zeep import Client, Settings
from zeep.exceptions import Fault
from zeep.plugins import HistoryPlugin
from zeep.xsd import SkipValue
from zeep.xsd.elements import Element
from zeep.xsd.types import AnyType, ComplexType

from odoo import _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

YURTICI_BARCODESERVICE_API_URL = {
    "prod": {
        "customer_integration_service": "https://ws.yurticikargo.com/KOPSWebServices/CustomerIntegrationService?wsdl",
        "scu_transfer_service": "https://ws.yurticikargo.com/KOPSWebServices/ScuTransferDocDataServices?wsdl",
        "reporting_service": "https://ws.yurticikargo.com/KOPSWebServices/WsReportWithReferenceServices?wsdl",
    },
    "test": {
        "customer_integration_service": "https://testws.yurticikargo.com/KOPSWebServices/CustomerIntegrationService?wsdl",
        "scu_transfer_service": "https://testws.yurticikargo.com/KOPSWebServices/ScuTransferDocDataServices?wsdl",
        "reporting_service": None,  # This is missing in the documentation
    },
}


class YurticiBarcodeRequest:
    """
    Interface for Yurtici Barcode Service API
    Handles customer and shipment operations for barcode service.
    """

    def __init__(
        self,
        username=None,
        password=None,
        customer_code=None,
        user_language="TR",
        prod=False,
    ):
        self.username = username or ""
        self.password = password or ""
        self.customer_code = customer_code or ""
        self.user_language = user_language or "TR"
        self.prod = prod
        api_env = "prod" if prod else "test"
        self.history = HistoryPlugin(maxlen=10)
        settings = Settings(strict=False, xml_huge_tree=True)
        self.customer_client = Client(
            wsdl=YURTICI_BARCODESERVICE_API_URL[api_env][
                "customer_integration_service"
            ],
            settings=settings,
            plugins=[self.history],
        )
        self.scu_client = Client(
            wsdl=YURTICI_BARCODESERVICE_API_URL[api_env]["scu_transfer_service"],
            settings=settings,
            plugins=[self.history],
        )

        self.reporting_client = Client(
            wsdl=YURTICI_BARCODESERVICE_API_URL[api_env]["reporting_service"],
            settings=settings,
            plugins=[self.history],
        )

    def _fill_defaults(self, schema_type, input_data):
        """
        Recursively fills missing fields in input_data to match schema_type.
        Missing fields are added as SkipValue.
        """
        if isinstance(schema_type, Element):
            schema_type = schema_type.type

        if isinstance(schema_type, ComplexType):
            for name, element in schema_type.elements:
                if name in input_data:
                    if isinstance(element.type, ComplexType | AnyType) and isinstance(
                        input_data[name], dict
                    ):
                        self._fill_defaults(element, input_data[name])
                else:
                    input_data[name] = SkipValue

    def _patch_vals(self, client, operation_name, vals):
        """
        Updates input_data in-place to ensure it matches the operation schema.
        Missing values are set to SkipValue.
        """
        service_name = list(client.wsdl.services.keys())[0]
        port_name = list(client.wsdl.services[service_name].ports.keys())[0]
        binding = client.wsdl.services[service_name].ports[port_name].binding

        operation = binding._operations[operation_name]
        input_type = operation.input.body.type

        self._fill_defaults(input_type, vals)

    def _barcode_api_credentials(self):
        """API credentials for Yurtici Barcode Web Services"""
        return {
            "wsUserName": self.username,
            "wsPassword": self.password,
            "wsUserLanguage": self.user_language,
        }

    def _tracking_api_credentials(self):
        """API credentials for Yurtici Tracking Web Services"""
        return {
            "userName": self.username,
            "password": self.password,
            "language": self.user_language,
        }

    def _process_reply(self, client, service, vals=None, send_as_kw=False):
        """Process API reply and handle errors"""

        try:
            if not send_as_kw:
                response = service(vals)
            else:
                response = service(**vals)
        except Fault:
            with client.settings(raw_response=True):
                if not send_as_kw:
                    response = service(vals)
                else:
                    response = service(**vals)
                try:
                    root = ET.fromstring(response.text)
                    error_text = next(root.iter("faultstring")).text
                    error_message = next(root.iter("message")).text
                    error_code = next(root.iter("code")).text
                    raise ValidationError(
                        f"Error in the request to the Yurtiçi API: "
                        f"[{error_text}] {error_code} - {error_message}"
                    )
                except ValidationError:
                    raise
                except Exception as e:
                    raise Fault(e) from e

        if getattr(response, "errCode", 0) or getattr(response, "outFlag", "0") != "0":
            raise ValidationError(
                _(
                    "%(out_result)s: %(err_code)s",
                    out_result=getattr(response, "outResult", ""),
                    err_code=getattr(response, "errCode", ""),
                )
            )

        return response

    def _save_customer(self, customer_vals):
        """Save customer and address information"""
        vals = self._barcode_api_credentials()
        vals.update(customer_vals)
        self._patch_vals(self.customer_client, "saveCustomerWithDeliveryInfo", vals)
        return self._process_reply(
            self.customer_client,
            self.customer_client.service.saveCustomerWithDeliveryInfo,
            vals,
            send_as_kw=True,
        )

    def _send_shipping(self, shipping_vals):
        """Create new shipment with barcode"""
        vals = self._barcode_api_credentials()
        vals.update(shipping_vals)
        self._patch_vals(self.scu_client, "createRoutingRequestWithZpl", vals)
        return self._process_reply(
            self.scu_client,
            self.scu_client.service.createRoutingRequestWithZpl,
            vals,
            send_as_kw=True,
        )

    def cancel_document(self, cancel_vals):
        """Cancel the expedition for the given cargo key"""
        vals = self._barcode_api_credentials()
        vals.update(cancel_vals)
        self._patch_vals(self.scu_client, "cancelDocument", vals)
        return self._process_reply(
            self.scu_client,
            self.scu_client.service.cancelDocument,
            vals,
            send_as_kw=True,
        )

    def track_document(self, track_vals):
        """Track the shipping status for the given cargo key using barcode service"""
        vals = self._tracking_api_credentials()
        vals.update(track_vals)
        self._patch_vals(
            self.reporting_client, "listInvDocumentInterfaceByReference", vals
        )
        return self._process_reply(
            self.reporting_client,
            self.reporting_client.service.listInvDocumentInterfaceByReference,
            vals,
            send_as_kw=True,
        )
