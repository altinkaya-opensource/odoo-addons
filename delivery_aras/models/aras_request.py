# Copyright 2024 Ahmet Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

# Copyright 2024 Ismail Cagan Yilmaz (https://github.com/milleniumkid)
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

import json
import logging
import os
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

from zeep import Client, Settings
from zeep.exceptions import Fault
from zeep.plugins import HistoryPlugin
from zeep.transports import Transport

from odoo import _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

ARAS_API_URL = {
    "prod": "https://customerws.araskargo.com.tr/arascargoservice.asmx?wsdl",
    "test": "https://customerservicestest.araskargo.com.tr/arascargoservice/arascargoservice.asmx?wsdl",
}

ARAS_QUERY_API_URL = {
    "prod": "https://customerservices.araskargo.com.tr/ArasCargoCustomerIntegrationService/ArasCargoIntegrationService.svc?wsdl",
    "test": "https://customerservicestest.araskargo.com.tr/ArasCargoIntegrationService.svc?singleWsdl",
}


class LocalSchemaTransport(Transport):
    """
    ref: https://github.com/mvantellingen/python-zeep/issues/1417
    Overrides Transport to accommodate local version of schema for http://schemas.xmlsoap.org/soap/encoding/
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def load(self, url):
        """Load the content from the given URL"""
        if not url:
            raise ValueError("No url given to load")

        scheme = urlparse(url).scheme
        if scheme in ("http", "https", "file"):
            if self.cache:
                response = self.cache.get(url)
                if response:
                    return bytes(response)

            # this url was causing some issues (404 errors);
            # it is now saved locally for fast retrieval when needed
            if url == "http://schemas.xmlsoap.org/soap/encoding/":
                base_dir = os.path.dirname(os.path.realpath(__file__))
                # Save soap-encodings.xml locally in the same directory as the script.
                soap_encodings_file = os.path.join(base_dir, "schemas.xmlsoap.org.xml")
                with open(soap_encodings_file, "rb") as fh:
                    return fh.read()

            content = self._load_remote_data(url)

            if self.cache:
                self.cache.add(url, content)

            return content
        else:
            with open(os.path.expanduser(url), "rb") as fh:
                return fh.read()


class ArasRequest:
    """Interface between Aras Kargo REST API and Odoo recordset
    Abstract Aras Kargo API Operations to connect them with Odoo

    Not all the features are implemented, but could be easily extended with
    the provided API. We leave the operations empty for future.
    """

    def __init__(
        self,
        username,
        password,
        query_username,
        query_password,
        customer_code,
        prod=False,
    ):
        self.username = username or ""
        self.password = password or ""
        self.query_username = query_username or ""
        self.query_password = query_password or ""
        self.customer_code = customer_code or ""
        api_env = "prod" if prod else "test"
        self.history = HistoryPlugin(maxlen=10)
        settings = Settings(strict=False, xml_huge_tree=True)
        self.client = Client(
            wsdl=ARAS_API_URL[api_env],
            settings=settings,
            plugins=[self.history],
            transport=LocalSchemaTransport(),
        )
        self.query_client = Client(
            wsdl=ARAS_QUERY_API_URL[api_env],
            settings=settings,
            plugins=[self.history],
            transport=LocalSchemaTransport(),
        )

    def _process_reply(self, service, vals=None):
        """Aras API returns error as server exceptions which makes zeep to
        raise a Fault exception as well. To catch the error info we need to make a
        raw_response request and the extract the error codes from the response."""
        try:
            response = service(**vals)
        except Fault as fault:
            error = ET.fromstring(fault)
            error_code = error.find("faultcode").text
            error_message = error.find("faultstring").text
            raise ValidationError(_(f"Error {error_code}: {error_message}")) from fault

        if type(response) is list:
            response = response[0]

        if int(response.ResultCode) != 0:
            raise ValidationError(
                f"{response.ResultCode}: "
                f"{hasattr(response, 'ResultMessage')
                and response.ResultMessage or response.Message}"
            )

        return response

    def _query_process_reply(self, service, vals=None):
        """We've selected JSON method for the query service. This method
        returns a JSON object which is easier to parse and use in the Odoo
        environment."""
        try:
            response = service(**vals)
            json_response = json.loads(response)
        except Exception as exc:
            raise ValidationError(
                _("Error in the request to the Aras API. %s") % exc
            ) from exc

        return json_response

    def _send_shipping(self, picking_vals):
        """Create new shipment
        :params vals dict of needed values
        :returns dict with Yurtici response containing the shipping code and label
        """
        vals = {"UserName": self.username, "Password": self.password}
        vals.update(picking_vals)
        final_vals = {
            "orderInfo": {"Order": vals},
            "userName": self.username,
            "password": self.password,
        }
        response = self._process_reply(self.client.service.SetOrder, final_vals)
        return response

    def _get_barcode(self, cargo_keys):
        """Get the barcode for the given ref
        :param str picking_name -- reference (picking name)
        :returns: str with barcode
        """
        vals = {
            "Username": self.username,
            "Password": self.password,
            "integrationCode": cargo_keys,
        }
        response = self._process_reply(self.client.service.GetBarcode, vals)
        return response.ZebraZpl

    def _cancel_shipment(self, cargo_keys):
        """Cancel the expedition for the given ref
        :param str picking_name -- reference (picking name)
        :returns: bool True if success
        """
        # vals = self._shipping_api_credentials()
        vals = {
            "userName": self.username,
            "password": self.password,
            "integrationCode": cargo_keys,
        }
        response = self._process_reply(self.client.service.CancelDispatch, vals)
        return response

    def _query_shipment(self, picking):
        """Get tracking status of the given ref
        :param stock.picking object
        :returns: Aras queryInfo object
        """
        vals = {
            "loginInfo": f"""<LoginInfo>
                    <UserName>{self.query_username}</UserName>
                    <Password>{self.query_password}</Password>
                    <CustomerCode>{self.customer_code}</CustomerCode>
                </LoginInfo>""",
            "queryInfo": f"""<QueryInfo>
                    <QueryType>1</QueryType>
                    <IntegrationCode>{picking.carrier_tracking_ref}</IntegrationCode>
                </QueryInfo>""",
        }
        response = self._query_process_reply(
            self.query_client.service.GetQueryJSON, vals
        )
        query_result = response["QueryResult"]
        if isinstance(query_result, dict):
            return query_result.get("Cargo")
        else:
            return False
