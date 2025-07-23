# Copyright 2022 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

# Copyright 2024 Ismail Cagan Yilmaz (https://github.com/milleniumkid)
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

import logging
from xml.etree import ElementTree as ET

from zeep import Client, Settings, xsd
from zeep.exceptions import Fault
from zeep.plugins import HistoryPlugin

from odoo import _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

YURTICI_API_URL = {
    "prod": "https://webservices.yurticikargo.com/KOPSWebServices/ShippingOrderDispatcherServices?wsdl",
    "test": "https://testwebservices.yurticikargo.com/KOPSWebServices/ShippingOrderDispatcherServices?wsdl",
}

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

# We were using zeep's get_type() method to get the xsd types, but it wasn't working
# properly, so we had to manually get the types from the wsdl file and create the
ShippingOrderV0_elements = [
    "cargoKey",
    "invoiceKey",
    "receiverCustName",
    "receiverAddress",
    "cityName",
    "townName",
    "receiverPhone1",
    "receiverPhone2",
    "receiverPhone3",
    "emailAddress",
    "taxOfficeId",
    "taxNumber",
    "taxOfficeName",
    "desi",
    "kg",
    "cargoCount",
    "waybillNo",
    "specialField1",
    "specialField2",
    "specialField3",
    "ttInvoiceAmount",
    "ttDocumentId",
    "ttCollectionType",
    "ttDocumentSaveType",
    "dcSelectedCredit",
    "dcCreditRule",
    "description",
    "orgGeoCode",
    "privilegeOrder",
    "custProdId",
    "orgReceiverCustId",
]


class YurticiRequest:
    """Interface between Yurtiçi Kargo REST API and Odoo recordset
    Abstract Aras Kargo API Operations to connect them with Odoo

    Not all the features are implemented, but could be easily extended with
    the provided API. We leave the operations empty for future.
    """

    def __init__(self, username=None, password=None, user_language=None, prod=False):
        self.username = username or ""
        self.password = password or ""
        self.user_language = user_language or ""
        api_env = "prod" if prod else "test"
        self.history = HistoryPlugin(maxlen=10)
        settings = Settings(strict=False, xml_huge_tree=True)
        self.client = Client(
            wsdl=YURTICI_API_URL[api_env],
            settings=settings,
            plugins=[self.history],
        )

    def _shipping_api_credentials(self):
        """API credentials for Yurtici Kargo Web Services"""
        return {
            "wsUserName": self.username,
            "wsPassword": self.password,
            "userLanguage": self.user_language,
        }

    def _process_reply(self, service, vals=None, send_as_kw=False):
        """Yurtiçi API returns error as server exceptions which makes zeep to
        raise a Fault exception as well. To catch the error info we need to make a
        raw_response request and the extract the error codes from the response."""
        try:
            if not send_as_kw:
                response = service(vals)
            else:
                response = service(**vals)
        except Fault:
            with self.client.settings(raw_response=True):
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
                        _(
                            f"""Error in the request to the Yurtiçi API. This is the
                            thrown message:\n\n
                            [{error_text}]\n
                            {error_code} - {error_message}"""
                        )
                    )
                except ValidationError:
                    raise
                # If we can't get the proper exception, fallback to the first
                # exception error traceback
                except Exception as e:
                    raise Fault(e) from e

        if response.outFlag != "0":
            raise ValidationError(
                f"{response.outResult}:\n{response.shippingOrderDetailVO[0].errMessage}"
            )

        return response

    def _fill_empty_fields(self, vals):
        """
        Fill empty fields with xsd.SkipValue (pass)
        :param vals: dict
        :return: dict
        """
        for field in ShippingOrderV0_elements:
            if field not in vals:
                vals[field] = xsd.SkipValue
        return vals

    def _send_shipping(self, shipment_array):
        """Create new shipment
        :params vals dict of needed values
        :returns dict with Yurtici response containing the shipping code and label
        """
        vals = self._shipping_api_credentials()
        filled_array = []

        for shipment in shipment_array:
            filled_array.append(self._fill_empty_fields(shipment))

        vals.update({"ShippingOrderVO": filled_array})
        response = self._process_reply(
            self.client.service.createShipment, vals, send_as_kw=True
        )
        return response.shippingOrderDetailVO[0]

    def _cancel_shipment(self, cargo_keys):
        """Cancel the expedition for the given ref
        :param str picking_name -- reference (picking name)
        :param int query_type -- yurtici_query_type field
        :returns: bool True if success
        """
        vals = self._shipping_api_credentials()
        vals.update({"cargoKeys": cargo_keys})
        response = self._process_reply(
            self.client.service.cancelShipment, vals, send_as_kw=True
        )
        return response

    def _query_shipment(self, picking):
        """Get tracking status of the given ref
        :param stock.picking object
        :returns: Yurtiçi queryShipment object
        """
        vals = self._shipping_api_credentials()
        vals["wsLanguage"] = vals.pop(
            "userLanguage"
        )  # this method requires the language field in wsLanguage
        vals.update(
            {
                "keys": picking.carrier_tracking_ref,
                "keyType": 0,  # 0 = ref_number, 1 = tracking_number
                "addHistoricalData": True,
                "onlyTracking": False,
            }
        )
        response = self._process_reply(
            self.client.service.queryShipment, vals, send_as_kw=True
        )
        return response.shippingDeliveryDetailVO[0]
