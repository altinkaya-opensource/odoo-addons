# Copyright (C) 2025 Ahmet Yiğit Budak (https://github.com/yibudak)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
import base64
import hashlib
import hmac
import json
import random
import string
from datetime import datetime

import requests

from odoo import _
from odoo.exceptions import ValidationError

from ..controllers.main import _IYZICO_RETURN_URL


class iyzicoConnector:
    def __init__(
        self,
        api_key,
        secret_key,
        base_url,
        tx,
        order_id=None,
        card_args=None,
        installment=None,
    ):
        self.api_key = api_key
        self.secret_key = secret_key.encode()  # Must be bytes
        self.base_url = base_url.rstrip("/")
        self.tx = tx
        self.env = tx.env  # To access env outside of tx
        self.order_id = order_id or self.tx.sale_order_ids
        self.card_args = card_args or {}
        self.installment = int(installment or 1)
        self._session = requests.Session()
        self._session.headers.update({"Accept": "application/json"})

    @property
    def conversation_id(self):
        return self.tx.reference or self._random_string(12)

    @property
    def locale(self):
        return "tr" if self.tx.partner_id.lang == "tr_TR" else "en"

    @property
    def source_currency(self):
        return self.tx.currency_id or self.order_id.currency_id

    @property
    def payment_currency(self):
        currency_try = self.env.ref("base.TRY")
        partner_country = (
            self.tx.partner_id or self.order_id.partner_id
        ).commercial_partner_id.country_id

        if self.source_currency != currency_try and partner_country.code == "TR":
            return currency_try

        return self.source_currency

    @property
    def installment_enabled(self):
        return self.tx.provider_id.iyzico_installment_enabled and self.installment > 1

    @staticmethod
    def _random_string(length=12):
        """Generate a random string of specified length.

        :param int length: The length of the random string.
        :return: A random string consisting of letters and digits.
        :rtype: str
        """
        return "".join(
            random.SystemRandom().choice(string.ascii_letters + string.digits)
            for _ in range(length)
        )

    @property
    def return_url(self):
        base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url")
        return f"{base_url}{_IYZICO_RETURN_URL}"

    def _get_card_number_formatted(self):
        """Get the card number formatted without spaces.

        :return: The card number without spaces.
        :rtype: str
        """
        return self.card_args.get("card_number", "").replace(" ", "")

    def _convert_price(self, price):
        """Convert the price to the payment currency if necessary.

        :param float price: The original price.
        :return: The converted and rounded price.
        :rtype: float
        """
        company_id = self.env.company

        if self.source_currency != self.payment_currency:
            price = self.source_currency._convert(
                price,
                self.payment_currency,
                company_id,
                datetime.today(),
            )
        return round(price, 2)

    def _generate_auth_headers(self, endpoint, request_body=None):
        """Generate authentication headers for Iyzico API requests.

        :param str endpoint: The API endpoint.
        :param str request_body: The request body as JSON string.
        :return: Dictionary of headers.
        :rtype: dict
        """
        rnd = self._random_string()
        data_to_encrypt = f"{rnd}{endpoint}{request_body or ''}"
        encrypted_data = hmac.new(
            self.secret_key,
            data_to_encrypt.encode(),
            hashlib.sha256,
        ).hexdigest()
        auth_string = (
            f"apiKey:{self.api_key}" f"&randomKey:{rnd}" f"&signature:{encrypted_data}"
        ).encode()
        return {
            "Authorization": "IYZWSv2 " + base64.b64encode(auth_string).decode(),
            "x-iyzi-rnd": rnd,
        }

    def _check_signature(self, response_data):
        """Check the signature of the response data for security.

        :param dict response_data: The response data from Iyzico.
        :return: True if signature is valid.
        :rtype: bool
        :raises AssertionError: If signature is invalid.
        """
        data_to_encrypt = f"{response_data["conversationId"]}:{response_data["token"]}"
        encrypted_data = hmac.new(
            self.secret_key,
            data_to_encrypt.encode(),
            hashlib.sha256,
        ).hexdigest()
        assert encrypted_data == response_data["signature"], _("Invalid signature")
        return True

    def _request(self, method, endpoint, data=None):
        """Make an authenticated request to the Iyzico API.

        :param str method: HTTP method (e.g., 'POST').
        :param str endpoint: API endpoint.
        :param dict data: Request data.
        :return: Response data.
        :rtype: dict
        """
        url = f"{self.base_url}{endpoint}"
        body = json.dumps(data) if data is not None else None
        headers = {"Content-Type": "application/json"} if data else {}

        headers.update(self._generate_auth_headers(endpoint, body))
        response = self._session.request(
            method, url, headers=headers, data=body, timeout=30
        )
        response.raise_for_status()

        response_data = response.json()
        # Post-request
        if response_data.get("token"):
            self._check_signature(response_data)
        return response_data

    def check_installment(self, price, card_number=None):
        """Check available installment options for a given price and card.

        :param float price: The transaction price.
        :param str card_number: The card number (optional).
        :return: Installment data from Iyzico.
        :rtype: dict
        """
        data = {
            "locale": self.locale,
            "price": self._convert_price(price),
            "conversationId": self.conversation_id,
        }
        if card_number:
            data["binNumber"] = card_number[:8]

        return self._request("POST", "/payment/iyzipos/installment", data)

    def _get_installed_included_price(self):
        """Calculate the total price including installment fees.

        :param float amount: The base amount.
        :return: The total amount including installment fees.
        :rtype: float
        """
        installment_amount = self.check_installment(
            self.tx.amount,
            self._get_card_number_formatted(),
        )
        installed_included_price = None
        for item in installment_amount.get("installmentDetails", []):
            for price_info in item.get("installmentPrices", []):
                if price_info["installmentNumber"] == self.installment:
                    installed_included_price = price_info["totalPrice"]

        if not installed_included_price:
            raise ValidationError(
                _(
                    "The selected installment option is not available."
                    "Please try again or select a different option."
                )
            )

        return installed_included_price

    def _prepare_buyer_data(self):
        """Prepare buyer data for Iyzico payment request.

        :return: Buyer information dictionary.
        :rtype: dict
        """
        partner = self.tx.partner_id.commercial_partner_id
        return {
            "id": str(partner.id),
            "name": partner.name,
            "surname": partner.name,
            "identityNumber": self.tx.partner_id.vat or "11111111111",
            "email": partner.email.split(",")[0] or "",
            "gsmNumber": partner.mobile or partner.phone or "",
            "registrationAddress": partner.contact_address or "",
            "city": partner.city or partner.state_id.name or "",
            "country": partner.country_id.name or "",
        }

    def _prepare_address_data(self, address_type):
        """Prepare address data for shipping or billing.

        :param str address_type: 'shipping' or 'billing'.
        :return: Address information dictionary.
        :rtype: dict
        """
        if self.tx.sale_order_ids:
            if address_type == "shipping":
                partner = self.tx.sale_order_ids.partner_shipping_id
            elif address_type == "billing":
                partner = self.tx.sale_order_ids.partner_invoice_id
        else:
            partner = self.tx.partner_id
        return {
            "contactName": partner.name,
            "city": partner.city or partner.state_id.name or "",
            "country": partner.country_id.name or "",
            "address": partner.contact_address or "",
        }

    def _prepare_basket_items_data(self):
        """Prepare basket items data for the payment request.

        :return: List of basket items.
        :rtype: list
        """
        items = []
        if self.tx.sale_order_ids:
            for line in self.tx.sale_order_ids.order_line:
                items.append(
                    {
                        "id": str(line.id),
                        "name": line.name,
                        "category1": line.product_id.categ_id.name or "",
                        "itemType": "VIRTUAL"
                        if line.product_id.type == "service"
                        else "PHYSICAL",
                        "price": self._convert_price(line.price_total),
                    }
                )
        else:
            items.append(
                {
                    "id": self.tx.reference,
                    "name": self.tx.reference,
                    "category1": "General",
                    "itemType": "VIRTUAL",
                    "price": self._convert_price(self.tx.amount),
                }
            )
        return items

    def _prepare_iyzico_price_vals(self, basket_items):
        """Prepare price values for Iyzico payment.

        :param list basket_items: List of basket items.
        :return: Price data dictionary.
        :rtype: dict
        """
        amount = sum(item["price"] for item in basket_items)

        if self.installment_enabled:
            paid_amount = self._get_installed_included_price()
        else:
            paid_amount = amount

        return {
            "price": amount,
            "paidPrice": paid_amount,
            "currency": self.payment_currency.name,
        }

    def _prepare_card_data(self):
        """Prepare card data for payment request.

        :return: Card information dictionary.
        :rtype: dict
        """
        return {
            "cardHolderName": self.card_args.get("card_name", ""),
            "cardNumber": self._get_card_number_formatted(),
            "expireMonth": self.card_args.get("card_valid_month", "").zfill(2),
            "expireYear": self.card_args.get("card_valid_year", "")[-2:],
            "cvc": self.card_args.get("card_cvv", ""),
        }

    def _prepare_payment_request_data(self):
        """Prepare the full payment request data for Iyzico.

        :return: Payment request data dictionary.
        :rtype: dict
        """
        base_data = {
            "locale": self.locale,
            "conversationId": self.conversation_id,
            # "basketId": self.tx.reference, # optional
            # "paymentGroup": "PRODUCT", # optional
            "callbackUrl": self.return_url,
            "buyer": self._prepare_buyer_data(),
            "shippingAddress": self._prepare_address_data("shipping"),
            "billingAddress": self._prepare_address_data("billing"),
            "basketItems": self._prepare_basket_items_data(),
            "paymentCard": self._prepare_card_data(),
        }
        # Add price related vals
        base_data.update(self._prepare_iyzico_price_vals(base_data["basketItems"]))

        if self.installment_enabled:
            base_data["installment"] = self.installment
        return base_data

    def _prepare_3ds_auth_data(self, response_data):
        """Prepare data for 3DS authentication response.

        :param dict response_data: Response data from 3DS initialization.
        :return: 3DS auth data dictionary.
        :rtype: dict
        """
        return {
            "locale": self.locale,
            "conversationId": self.conversation_id,
            "paymentId": response_data["paymentId"],
            "conversationData": response_data["conversationData"],
        }

    def initialize_3ds_process(self):
        """Initialize the 3DS payment process.

        :return: 3DS HTML content.
        :rtype: str
        :raises ValidationError: If initialization fails.
        """
        data = self._prepare_payment_request_data()
        response = {}
        try:
            response = self._request("POST", "/payment/3dsecure/initialize", data)
            return response["threeDSHtmlContent"]
        except KeyError:
            raise ValidationError(response["errorMessage"])
        except Exception:
            raise ValidationError(
                _("An error occurred. Please contact the administrator.")
            )

    def make_non_3ds_payment(self):
        """Make a non-3DS payment.

        :return: Tuple of status and response data.
        :rtype: tuple
        :raises ValidationError: If payment fails.
        """
        data = self._prepare_payment_request_data()
        response = {}
        try:
            res = self._request("POST", "/payment/auth", data)
            if res.get("status") == "success":
                return ("success", res)
            else:
                return ("error", f"({res.get('errorCode')}) {res.get('errorMessage')}")
        except KeyError:
            raise ValidationError(response["errorMessage"])
        except Exception:
            raise ValidationError(
                _("An error occurred. Please contact the administrator.")
            )

    def auth_3ds_response(self, response_data):
        """Authenticate the 3DS response.

        :param dict response_data: 3DS response data.
        :return: Tuple of status and response data or error message.
        :rtype: tuple or str
        """
        try:
            data = self._prepare_3ds_auth_data(response_data)
            res = self._request("POST", "/payment/3dsecure/auth", data)
            if res.get("status") == "success" and res.get("mdStatus") == 1:
                return ("success", res)
            else:
                return ("error", f"({res.get('errorCode')}) {res.get('errorMessage')}")
        except Exception as e:
            return str(e)
