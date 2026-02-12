# Copyright 2022 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
import logging
from hashlib import sha256

import requests

from odoo import _, fields, models
from odoo.exceptions import ValidationError

from ..const import MOKA_ERRORS, PROD_URL, TEST_URL

_logger = logging.getLogger(__name__)


class PaymentProvider(models.Model):
    _inherit = "payment.provider"

    code = fields.Selection(
        selection_add=[("moka", "MOKA")], ondelete={"moka": "set default"}
    )
    moka_dealer_code = fields.Char(
        help="Dealer code issued by the Moka system",
        required_if_provider="moka",
    )
    moka_username = fields.Char(
        help="Api username given by Moka system",
        groups="base.group_system",
    )
    moka_password = fields.Char(
        help="Api password given by Moka system",
        groups="base.group_system",
    )

    def _moka_get_api_url(self):
        """Return the API URL according to the provider state.

        Note: self.ensure_one()

        :return: The API URL
        :rtype: str
        """
        self.ensure_one()

        if self.state == "enabled":
            return PROD_URL
        else:
            return TEST_URL

    def _moka_format_card_number(self, card_number):
        """
        This method is used to format the card number
        :param card_number: The card number
        :return: The formatted card number
        """
        card_number = card_number.replace(" ", "")
        if len(card_number) == 16 and card_number.isdigit():
            return card_number
        else:
            raise ValidationError(_("Card number is not valid."))

    def _moka_get_check_key(self):
        """Compute the check key for the given provider.
        sha256(DealerCode + "MK" + Username + "PD" + Password)
        :return: The check key
        :rtype: str
        """
        self.ensure_one()
        key_string = (
            f"{self.moka_dealer_code}MK{self.moka_username}PD{self.moka_password}"
        )

        return sha256(key_string.encode("utf-8")).hexdigest()

    def _moka_get_return_url(self):
        """
        This method is used to get the return url for the Moka API
        :return: The return url
        """
        self.ensure_one()
        return (
            self.env["ir.config_parameter"].sudo().get_param("web.base.url")
            + "/payment/moka/return"
        )

    def _moka_get_auth_vals(self):
        """
        This method is used to get the authentication values for the Moka API
        :return: The authentication values
        """
        self.ensure_one()
        return {
            "DealerCode": self.moka_dealer_code,
            "Username": self.moka_username,
            "Password": self.moka_password,
            "CheckKey": self._moka_get_check_key(),
        }

    def _moka_get_currency(self, currency):
        """
        This method is used to get the currency code of the given currency
        :param currency: The currency id
        :return: The currency code
        """
        self.ensure_one()
        currency_name = "TL"
        currency_id = self.env["res.currency"].browse(currency)
        if currency_id.name != "TRY":
            currency_name = currency_id.name
        return currency_name

    def _moka_get_payment_vals(self, tx, amount, currency, card_args, client_ip):
        return {
            "PaymentDealerAuthentication": self._moka_get_auth_vals(),
            "PaymentDealerRequest": {
                "CardHolderFullName": card_args.get("card_name"),
                "CardNumber": self._moka_format_card_number(
                    card_args.get("card_number")
                ),
                "ExpMonth": card_args.get("card_valid_month").zfill(2),
                "ExpYear": card_args.get("card_valid_year"),
                "CvcNumber": card_args.get("card_cvv"),
                "Amount": amount,
                "Currency": self._moka_get_currency(currency),
                "InstallmentNumber": 1,  # Taksit alanı, 0 veya 1 peşin demek.
                "ClientIP": client_ip,
                "OtherTrxCode": tx.reference,
                "IsPoolPayment": 0,
                "IsPreAuth": 0,
                "IsTokenized": 0,
                "Software": "Odoo",
                "ReturnHash": 1,
                "RedirectUrl": self._moka_get_return_url(),
            },
        }

    def _moka_make_payment_request(self, tx, amount, currency, card_args, client_ip):
        """
        This method is used to make a payment request to the Moka API
        :param tx: The transaction
        :param amount: The amount of the transaction
        :param currency: The currency of the transaction
        """
        self.ensure_one()
        vals = self._moka_get_payment_vals(tx, amount, currency, card_args, client_ip)

        try:
            resp = requests.post(
                f"{self._moka_get_api_url()}/PaymentDealer/DoDirectPaymentThreeD",
                json=vals,
                timeout=10,
            )

        except requests.exceptions.Timeout:
            raise ValidationError(_("Moka: Timeout. Please try again."))  # noqa: B904

        if resp.status_code != 200:
            raise ValidationError(_("Payment request failed."))

        resp_json = resp.json()
        result_code = resp_json.get("ResultCode")
        if result_code != "Success":
            raise ValidationError(MOKA_ERRORS.get(result_code, result_code))

        return resp_json.get("Data")

    def _moka_validate_card_args(self, card_args):
        """
        Validation method for credit/debit card information
        :param card_args: The card information
        :return: error message if there is any error
        """
        error = ""
        card_number = card_args.get("card_number")
        card_cvv = card_args.get("card_cvv")
        if not card_number or len(card_number) < 16:
            error += _("Card number is not valid.\n")

        if not card_cvv or len(card_cvv) < 3:
            error += _("Card CVV is not valid.\n")

        if not card_args.get("card_name"):
            error += _("Card name is not valid.\n")

        if not card_args.get("card_valid_month") or not card_args.get(
            "card_valid_year"
        ):
            error += _("Card expiration date is not valid.\n")
        return error
