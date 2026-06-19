# Copyright 2025 Ahmet Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
import logging

from odoo import _, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.misc import format_amount

from ..const import PROD_URL, TEST_URL
from .iyzico_connector import iyzicoConnector

_logger = logging.getLogger(__name__)


class PaymentProvider(models.Model):
    _inherit = "payment.provider"

    code = fields.Selection(
        selection_add=[("iyzico_altinkaya", "iyzico Sanal Pos")],
        ondelete={"iyzico_altinkaya": "set default"},
    )
    iyzico_api_key = fields.Char(
        "API Key",
        help="API Key provided by Iyzico Sanal Pos",
        required_if_provider="iyzico_altinkaya",
        groups="base.group_user",
    )
    iyzico_secret_key = fields.Char(
        "Secret Key",
        help="Secret Key provided by Iyzico Sanal Pos",
        required_if_provider="iyzico_altinkaya",
        groups="base.group_user",
    )
    iyzico_installment_enabled = fields.Boolean(
        "Enable Installments",
        help="Enable installment options during checkout",
        default=True,
    )
    iyzico_3ds_threshold_amount = fields.Monetary(
        "3DS Threshold Amount",
        help="Transactions above this amount will require 3D Secure authentication. "
        "Set to 0 to always require 3D Secure authentication.",
        default=0.0,
        currency_field="iyzico_currency_try_id",
    )
    iyzico_currency_try_id = fields.Many2one(
        "res.currency",
        string="TRY Currency",
        help="Currency in which the 3DS threshold amount is defined. "
        "It is recommended to set this to Turkish Lira (TRY).",
        readonly=True,
        default=lambda self: self.env.ref("base.TRY"),
    )

    def _get_iyzico_connector(
        self,
        tx,
        order_id=None,
        card_args=None,
        installment=None,
        temp_currency_id=None,
        partner_id=None,
    ):
        """Create and return an Iyzico connector instance.

        :param tx: The payment transaction record.
        :param order_id: The sale order record (optional).
        :param dict card_args: The card information arguments (optional).
        :param int installment: The installment number (optional).
        :return: An iyzicoConnector instance.
        :rtype: iyzicoConnector
        """
        return iyzicoConnector(
            api_key=self.iyzico_api_key,
            secret_key=self.iyzico_secret_key,
            base_url=self._iyzico_get_api_url(),
            tx=tx,
            order_id=order_id,
            card_args=card_args,
            installment=installment,
            temp_currency_id=temp_currency_id,
            partner_id=partner_id,
        )

    def iyzico_enable_3ds_mode(self, connector, force_3ds=False):
        """Determine whether to enable 3DS payment mode based on transaction details.

        :param tx: The payment transaction record.
        :param force_3ds: Boolean to force 3DS payment mode.
        :return: True if 3DS should be enabled, False for non-3DS.
        :rtype: bool
        """
        self.ensure_one()
        return True
        # if force_3ds:
        #     return True

        # partner = connector.tx.partner_id.commercial_partner_id
        # # Disable 3DS for non-Turkish partners (international transactions)
        # if partner.country_id and partner.country_id.code != "TR":
        #     return False

        # # Disable 3DS if amount is below threshold in TRY
        # if (
        #     connector.payment_currency == self.iyzico_currency_try_id
        #     and connector._convert_price(connector.tx.amount)
        #     <= self.iyzico_3ds_threshold_amount
        # ):
        #     return False

        # return True

    def _iyzico_initialize_payment(
        self, tx, card_args, installment=None, force_3ds=False
    ):
        """Initialize the payment process with Iyzico.

        :param tx: The payment transaction record.
        :param dict card_args: The card information arguments.
        :param int installment: The installment number (optional).
        :return: Tuple of payment method and gateway response.
        :rtype: tuple
        """
        self.ensure_one()
        tx.ensure_one()
        connector = self._get_iyzico_connector(
            tx, card_args=card_args, installment=installment
        )
        if self.iyzico_enable_3ds_mode(connector, force_3ds=force_3ds):
            return ("3ds", connector.initialize_3ds_process())
        else:
            return ("non_3ds", connector.make_non_3ds_payment())

    def iyzico_check_installment(
        self, card_number, price, order_id, tx, temp_currency_id, partner_id
    ):
        """Fetch installment options for a given card number and amount.

        :param str card_number: The card number to fetch installment options for.
        :param float price: The price amount for the transaction.
        :param order_id: The sale order record.
        :param tx: The payment transaction record (dummy recordset).
        :return: List of installment options.
        :rtype: list
        """
        installment_options = []
        connector = self._get_iyzico_connector(
            tx, order_id, temp_currency_id=temp_currency_id, partner_id=partner_id
        )
        # Base amount in the payment currency (iyzico totals are already
        # expressed in it), so the installment fee subtraction is consistent.
        converted_base = connector._convert_price(price)
        _iyz_options = connector.check_installment(price, card_number=card_number)
        if _iyz_options["status"] == "success":
            for item in _iyz_options["installmentDetails"][0]["installmentPrices"]:
                installment_fee = item["totalPrice"] - converted_base
                installment_options.append(
                    {
                        "installmentNumber": item["installmentNumber"],
                        "totalPrice": format_amount(
                            self.env, item["totalPrice"], connector.payment_currency
                        ),
                        "monthlyPrice": format_amount(
                            self.env,
                            item["totalPrice"] / item["installmentNumber"],
                            connector.payment_currency,
                        ),
                        "baseAmount": format_amount(
                            self.env, converted_base, connector.payment_currency
                        ),
                        # Raw values so the storefront can render the fee and
                        # the fee-inclusive total in its order summary.
                        "installmentFee": round(installment_fee, 2),
                        "totalAmount": round(item["totalPrice"], 2),
                        "currency": connector.payment_currency.name,
                    }
                )
        return installment_options

    def _iyzico_get_api_url(self):
        """Return the API URL according to the provider state.

        :return: The API URL.
        :rtype: str
        """
        self.ensure_one()

        if self.state == "enabled":
            return PROD_URL
        else:
            return TEST_URL

    def _iyzico_format_card_number(self, card_number):
        """Format the card number for validation.

        :param str card_number: The card number to format.
        :return: The formatted card number.
        :rtype: str
        :raises ValidationError: If the card number is invalid.
        """
        card_number = card_number.replace(" ", "")
        if len(card_number) in [15, 16] and card_number.isdigit():
            return card_number
        else:
            raise ValidationError(_("Card number is not valid."))

    def _iyzico_validate_card_args(self, card_args):
        """Validate credit/debit card information.

        :param dict card_args: The card information arguments.
        :return: Error message if validation fails, empty string otherwise.
        :rtype: str
        """
        error = ""
        card_number = self._iyzico_format_card_number(card_args.get("card_number"))
        card_cvv = card_args.get("card_cvv")
        if not card_number or len(card_number) < 15:
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
