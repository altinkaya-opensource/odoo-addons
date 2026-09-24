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
import logging
import random
import string
import time
from datetime import datetime

import requests

from odoo import _, fields
from odoo.exceptions import ValidationError

from ..const import REQUEST_TIMEOUT, RETRY_BACKOFF, RETRY_COUNT
from ..controllers.main import _IYZICO_RETURN_URL

_logger = logging.getLogger(__name__)


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
        temp_currency_id=None,
        partner_id=None,
    ):
        self.api_key = api_key
        self.secret_key = secret_key.encode()  # Must be bytes
        self.base_url = base_url.rstrip("/")
        self.tx = tx
        self.env = tx.env  # To access env outside of tx
        self.order_id = order_id or self.tx.sale_order_ids
        self.temp_currency_id = temp_currency_id
        self.partner_id = partner_id or self.tx.partner_id or self.order_id.partner_id
        self.card_args = card_args or {}
        self.installment = int(installment or 1)
        self._session = requests.Session()
        self._session.headers.update({"Accept": "application/json"})

    @property
    def conversation_id(self):
        return self.tx.reference or self._random_string(12)

    @property
    def locale(self):
        return "tr" if self.partner_id.lang == "tr_TR" else "en"

    @property
    def source_currency(self):
        return self.tx.currency_id or self.order_id.currency_id or self.temp_currency_id

    @property
    def payment_currency(self):
        currency_try = self.env.ref("base.TRY")
        partner_country = (self.partner_id).commercial_partner_id.country_id

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
            f"apiKey:{self.api_key}&randomKey:{rnd}&signature:{encrypted_data}"
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
        data_to_encrypt = f"{response_data['conversationId']}:{response_data['token']}"
        encrypted_data = hmac.new(
            self.secret_key,
            data_to_encrypt.encode(),
            hashlib.sha256,
        ).hexdigest()
        assert encrypted_data == response_data["signature"], _("Invalid signature")
        return True

    def _request(self, method, endpoint, data=None, retries=0):
        """Make an authenticated request to the Iyzico API.

        :param str method: HTTP method (e.g., 'POST').
        :param str endpoint: API endpoint.
        :param dict data: Request data.
        :param int retries: How many times to retry when iyzico cannot be
            reached. Pass a non-zero value only for endpoints that cannot move
            money: a reset connection is no proof that iyzico did not process
            the request.
        :return: Response data.
        :rtype: dict
        """
        url = f"{self.base_url}{endpoint}"
        body = json.dumps(data) if data is not None else None
        headers = {"Content-Type": "application/json"} if data else {}

        headers.update(self._generate_auth_headers(endpoint, body))
        for attempt in range(retries + 1):
            try:
                response = self._session.request(
                    method, url, headers=headers, data=body, timeout=REQUEST_TIMEOUT
                )
                break
            except requests.ConnectionError:
                # Read timeouts are deliberately not retried: the request
                # already reached iyzico and the customer has waited the full
                # timeout for it.
                if attempt == retries:
                    raise
                _logger.warning(
                    "[iyzico] %s unreachable, retrying (%s/%s)",
                    endpoint,
                    attempt + 1,
                    retries,
                )
                time.sleep(RETRY_BACKOFF * (attempt + 1))

        response.raise_for_status()

        response_data = response.json()
        # Post-request
        if response_data.get("token"):
            self._check_signature(response_data)
        return response_data

    def check_installment(self, price, card_number=None):
        """Check available installment options for a given price and card.

        Read-only call, so it is retried while iyzico is unreachable.

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

        return self._request(
            "POST", "/payment/iyzipos/installment", data, retries=RETRY_COUNT
        )

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
        partner = self.partner_id
        return {
            "id": str(partner.id),
            "name": partner.name,
            "surname": partner.name,
            "identityNumber": self.tx.partner_id.vat or "11111111111",
            "email": (partner.email or "").split(",")[0].strip(),
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
                partner = self.order_id.partner_shipping_id
            elif address_type == "billing":
                partner = self.order_id.partner_invoice_id
        else:
            partner = self.partner_id
        return {
            "contactName": partner.name,
            "city": partner.city or partner.state_id.name or "",
            "country": partner.country_id.name or "",
            "address": partner.contact_address or "",
        }

    def _prepare_basket_items_data(self):
        """Prepare basket items data for the payment request.

        To handle all scenarios, we include only the first positive line
        from the order as the basket item. This ensures compatibility
        with iyzico and Odoo's promotion mechanisms.

        :return: List of basket items.
        :rtype: list
        """
        items = []
        first_line = fields.first(
            self.order_id.order_line.filtered(lambda ol: ol.price_total > 0)
        )
        if first_line:
            items.append(
                {
                    "id": str(first_line.id),
                    "name": first_line.name[:200],  # iyzico limit
                    "category1": first_line.product_id.categ_id.name or "",
                    "itemType": "VIRTUAL"
                    if first_line.product_id.type == "service"
                    else "PHYSICAL",
                    "price": self._convert_price(self.tx.amount),
                }
            )
        else:
            # Fallback: if no positive lines, use transaction reference
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
        amount = round(sum(item["price"] for item in basket_items), 2)

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

        No money moves at this step, so the call is retried while iyzico is
        unreachable.

        :return: 3DS HTML content.
        :rtype: str
        :raises ValidationError: If initialization fails.
        """
        data = self._prepare_payment_request_data()
        response = {}
        try:
            response = self._request(
                "POST", "/payment/3dsecure/initialize", data, retries=RETRY_COUNT
            )
            html_content = response["threeDSHtmlContent"]
            if response.get("paymentId"):
                # Trust the authenticated initialization response, not the
                # payment ID subsequently supplied to the public callback.
                self.tx.provider_reference = str(response["paymentId"])
            return html_content
        except KeyError:
            raise ValidationError(
                response.get("errorMessage")
                or _("An error occurred. Please contact the administrator.")
            )
        except Exception:
            _logger.exception(
                "[iyzico] 3DS initialization failed for %s", self.conversation_id
            )
            raise ValidationError(
                _("An error occurred. Please contact the administrator.")
            )

    def make_non_3ds_payment(self):
        """Make a non-3DS payment.

        This call charges the card, so it is never retried.

        :return: ``(status, payload)``; see `auth_3ds_response` for the meaning
            of each status.
        :rtype: tuple
        """
        data = self._prepare_payment_request_data()
        try:
            res = self._request("POST", "/payment/auth", data)
        except requests.RequestException as e:
            _logger.exception(
                "[iyzico] payment left unconfirmed for %s", self.conversation_id
            )
            return ("unknown", str(e))
        except Exception as e:
            _logger.exception("[iyzico] payment failed for %s", self.conversation_id)
            return ("error", str(e))

        if res.get("status") == "success":
            return ("success", res)
        return ("error", f"({res.get('errorCode')}) {res.get('errorMessage')}")

    def auth_3ds_response(self, response_data):
        """Authenticate the 3DS response.

        This call charges the card, so it is never retried.

        :param dict response_data: 3DS response data.
        :return: ``(status, payload)``. ``success`` carries the iyzico
            response, ``error`` an error message, and ``unknown`` means iyzico
            never confirmed the outcome, so the card may or may not have been
            charged.
        :rtype: tuple
        """
        try:
            data = self._prepare_3ds_auth_data(response_data)
            res = self._request("POST", "/payment/3dsecure/auth", data)
        except requests.RequestException as e:
            _logger.exception(
                "[iyzico] 3DS auth unanswered for paymentId %s",
                response_data.get("paymentId"),
            )
            return ("unknown", str(e))
        except Exception as e:
            _logger.exception(
                "[iyzico] 3DS auth failed for paymentId %s",
                response_data.get("paymentId"),
            )
            return ("error", str(e))

        if res.get("status") == "success" and res.get("mdStatus") == 1:
            return ("success", res)
        return ("error", f"({res.get('errorCode')}) {res.get('errorMessage')}")

    def retrieve_payment(self, payment_id=None, conversation_id=None):
        """Ask iyzico for the final state of a payment it never confirmed.

        Read-only call, so it is retried while iyzico is unreachable.

        :param str payment_id: The iyzico payment id, when one was recorded.
        :param str conversation_id: The conversation id of the original
            payment request, used when no payment id is available.
        :return: Response data, including the `paymentStatus` of the payment.
        :rtype: dict
        """
        data = {"locale": self.locale, "conversationId": self.conversation_id}
        if payment_id:
            data["paymentId"] = payment_id
        else:
            data["paymentConversationId"] = conversation_id

        return self._request("POST", "/payment/detail", data, retries=RETRY_COUNT)
