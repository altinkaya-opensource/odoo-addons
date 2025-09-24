# Copyright 2025 Ahmet Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
import logging

from odoo import _, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.payment import utils as payment_utils

from .iyzico_connector import iyzicoConnector

_logger = logging.getLogger(__name__)


class PaymentTransaction(models.Model):
    _inherit = "payment.transaction"

    iyzico_installment_fee = fields.Monetary(
        string="iyzico Installment Fee",
        help="The commission amount charged by Iyzico for this transaction",
        readonly=True,
        currency_field="iyzico_commission_currency_id",
        copy=False,
    )
    iyzico_commission_currency_id = fields.Many2one(
        "res.currency",
        string="Iyzico Commission Currency",
        help="Currency of the Iyzico commission amount",
        readonly=True,
        default=lambda self: self.env.ref("base.TRY"),
        copy=False,
    )

    # === BUSINESS METHODS ===#

    def _iyzico_compute_access_token(
        self, reference=None, amount=None, partner_id=None
    ):
        """Return the expected access token for Iyzico transactions.

        This can work with payment.transaction recordset or payment dictionary.

        :param str reference: Transaction reference.
        :param float amount: Transaction amount.
        :param int partner_id: Partner ID.
        :return: Access token or False.
        :rtype: str or bool
        """
        self.ensure_one()
        if self.provider_code != "iyzico_altinkaya":
            return False

        reference = reference or self.reference
        amount = amount or self.amount
        partner_id = partner_id or self.partner_id.id

        return payment_utils.generate_access_token(reference, amount, partner_id)

    def _iyzico_ensure_access_token(self, access_token):
        """Ensure the access token is valid.

        Note: self.ensure_one()

        :param str access_token: The access token to validate
        :return: None
        :raise: ValidationError if the access token is invalid
        """
        expected_access_token = self._iyzico_compute_access_token()
        if not expected_access_token:
            return

        assert access_token == expected_access_token

    def _get_specific_processing_values(self, processing_values):
        """Override of payment to return Iyzico-specific processing values.

        Note: self.ensure_one() from `_get_processing_values`

        :param dict processing_values: The generic processing values of the transaction
        :return: The dict of provider-specific processing values
        :rtype: dict
        """
        res = super()._get_specific_processing_values(processing_values)
        if self.provider_code != "iyzico_altinkaya":
            return res

        res["access_token"] = self._iyzico_compute_access_token(
            reference=processing_values.get("reference"),
            amount=processing_values.get("amount"),
            partner_id=processing_values.get("partner_id"),
        )
        return res

    def _iyzico_set_amounts(self, response):
        """Set the commission data from the Iyzico response.s

        :param dict response: Response data from Iyzico.
        :return: bool
        """
        currency_id = self.env["res.currency"].search(
            [("name", "=", response.get("currency"))], limit=1
        )
        paid_amount = response.get("paidPrice", self.amount)
        installment_fee = response.get("merchantCommissionRateAmount", 0)
        self.write(
            {
                "amount": paid_amount,
                "currency_id": currency_id.id,
                "iyzico_installment_fee": installment_fee,
            }
        )
        return True

    def _iyzico_finalize_payment(self, status, response):
        """Finalize the payment based on status and response.

        :param str status: Payment status ('success' or 'error').
        :param dict response: Response data from iyzico.
        :return: None
        """
        try:
            if status == "success":
                self._set_done()
                # When setting iyzico amounts, there could be mismatch in amounts
                # due to installment fees. So, firstly confirm the order to lock the
                # amount, then set the amounts from iyzico response.
                self._check_amount_and_confirm_order()
                self._iyzico_set_amounts(response)
            else:
                self._set_error(response)
        except Exception as e:
            _logger.warning(
                "iyzico payment error: %s, data: %s", (e, response), exc_info=True
            )
            self._set_error(
                _("Something went wrong during the payment. Please try again.")
            )

    def _process_notification_data(self, notification_data):
        """Override of payment to process the transaction based on iyzico data.

        Note: self.ensure_one()

        :param dict notification_data: The notification data sent by the provider
        :return: None
        :raise: ValidationError if inconsistent data were received
        """
        super()._process_notification_data(notification_data)
        if self.provider_code != "iyzico_altinkaya":
            return

        self.operation = "online_redirect"
        self.provider_reference = notification_data.get("paymentId")
        if notification_data.get("status") == "success":
            connector = iyzicoConnector(
                api_key=self.provider_id.iyzico_api_key,
                secret_key=self.provider_id.iyzico_secret_key,
                base_url=self.provider_id._iyzico_get_api_url(),
                tx=self,
            )
            res = connector.auth_3ds_response(notification_data)
            self._iyzico_finalize_payment(*res)

        else:
            self._set_error(
                _("3DS: Something went wrong during the payment. Please try again.")
            )

    def _get_tx_from_notification_data(self, provider_code, notification_data):
        """Override of payment to find the transaction based on iyzico data.

        :param str provider_code: The code of the provider that handled the transaction
        :param dict notification_data: The notification data sent by the provider
        :return: The transaction if found
        :rtype: recordset of `payment.transaction`
        :raise: ValidationError if inconsistent data were received
        :raise: ValidationError if the data match no transaction
        """
        tx = super()._get_tx_from_notification_data(provider_code, notification_data)
        if provider_code != "iyzico_altinkaya" or len(tx) == 1:
            return tx

        tx_code = notification_data.get("conversationId")
        if not tx_code:
            raise ValidationError(
                _("iyzico: Received data with missing transaction code.")
            )

        tx = self.search(
            [
                ("reference", "=", tx_code),
                ("state", "not in", ("done", "cancel", "error")),
            ],
            limit=1,
            order="id desc",
        )

        if not tx:
            raise ValidationError(
                _(
                    "iyzico: No transaction found matching reference %(tx_code)s.",
                    tx_code=tx_code,
                )
            )
        return tx
