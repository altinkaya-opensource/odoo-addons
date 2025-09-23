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

    @staticmethod
    def _random_string(length=12):
        return "".join(
            random.SystemRandom().choice(string.ascii_letters + string.digits)
            for _ in range(length)
        )

    @property
    def return_url(self):
        base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url")
        return f"{base_url}{_IYZICO_RETURN_URL}"

    def _convert_price(self, price):
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
        data_to_encrypt = f"{response_data["conversationId"]}:{response_data["token"]}"
        encrypted_data = hmac.new(
            self.secret_key,
            data_to_encrypt.encode(),
            hashlib.sha256,
        ).hexdigest()
        assert encrypted_data == response_data["signature"], _("Invalid signature")
        return True

    def _request(self, method, endpoint, data=None):
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
        data = {
            "locale": self.locale,
            "price": self._convert_price(price),
            "conversationId": self.conversation_id,
        }
        if card_number:
            data["binNumber"] = card_number[:8]

        return self._request("POST", "/payment/iyzipos/installment", data)

    def _get_enabled_installments(self):
        """Return a list of enabled installment options.

        If no option is enabled, return an empty list which means all options are
        enabled.
        """
        try:
            # TODO: I'm not sure if this is the correct way to get available
            # installments. Please check and correct if necessary.
            data = self.check_installment(self.tx.amount)
            installment_details = data["installmentDetails"]
            any_issuer = installment_details[0]
            return [x["installmentNumber"] for x in any_issuer["installmentPrices"]]
        except Exception:
            return []

    def _prepare_buyer_data(self):
        partner = self.tx.partner_id.commercial_partner_id
        return {
            "id": str(partner.id),
            "name": partner.name,
            "surname": partner.name,
            "identityNumber": self.tx.partner_id.vat or "11111111111",
            "email": partner.email or "",
            "gsmNumber": partner.mobile or partner.phone or "",
            "registrationAddress": partner.contact_address or "",
            "city": partner.city or partner.state_id.name or "",
            "country": partner.country_id.name or "",
        }

    def _prepare_address_data(self, address_type):
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
        amount = sum(item["price"] for item in basket_items)
        return {
            "price": amount,
            "paidPrice": amount,
            "currency": self.payment_currency.name,
        }

    def _prepare_card_data(self):
        return {
            "cardHolderName": self.card_args.get("card_name", ""),
            "cardNumber": self.card_args.get("card_number", "").replace(" ", ""),
            "expireMonth": self.card_args.get("card_valid_month", "").zfill(2),
            "expireYear": self.card_args.get("card_valid_year", "")[-2:],
            "cvc": self.card_args.get("card_cvv", ""),
        }

    def _prepare_payment_request_data(self):
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

        if self.tx.provider_id.iyzico_installment_enabled:
            base_data["installment"] = self.installment
        return base_data

    def _prepare_3ds_auth_data(self, response_data):
        return {
            "locale": self.locale,
            "conversationId": self.conversation_id,
            "paymentId": response_data["paymentId"],
            "conversationData": response_data["conversationData"],
        }

    def initialize_3ds_process(self):
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
        try:
            data = self._prepare_3ds_auth_data(response_data)
            res = self._request("POST", "/payment/3dsecure/auth", data)
            if res.get("status") == "success" and res.get("mdStatus") == 1:
                return ("success", res)
            else:
                return ("error", f"({res.get('errorCode')}) {res.get('errorMessage')}")
        except Exception as e:
            return str(e)
