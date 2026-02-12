# Copyright 2022 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
import logging
from hashlib import sha256

from odoo import _, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.payment import utils as payment_utils

from ..const import MOKA_3D_ERRORS

_logger = logging.getLogger(__name__)


class PaymentTransaction(models.Model):
    _inherit = "payment.transaction"

    moka_tx_code = fields.Char(
        string="Moka Transaction Code", readonly=True, copy=False
    )
    moka_success_hash = fields.Char(readonly=True, copy=False)
    moka_fail_hash = fields.Char(string="Moka Failure Hash", readonly=True, copy=False)

    # === BUSINESS METHODS ===#

    def _get_specific_processing_values(self, processing_values):
        """Override of payment to return  Moka-specific processing values.

        Note: self.ensure_one() from `_get_processing_values`

        :param dict processing_values: The generic processing values of the transaction
        :return: The dict of provider-specific processing values
        :rtype: dict
        """
        res = super()._get_specific_processing_values(processing_values)
        if self.provider_code != "moka":
            return res

        return {
            "access_token": payment_utils.generate_access_token(
                processing_values["reference"],
                processing_values["amount"],
                processing_values["partner_id"],
            )
        }

    def _moka_calculate_tx_hashes(self, unique_code):
        self.ensure_one()
        success_hash = sha256((unique_code + "T").encode("utf-8")).hexdigest()
        fail_hash = sha256((unique_code + "F").encode("utf-8")).hexdigest()
        self.write(
            {
                "moka_success_hash": success_hash,
                "moka_fail_hash": fail_hash,
            }
        )
        return True

    def _process_notification_data(self, notification_data):
        """Override of payment to process the transaction based on Moka data.

        Note: self.ensure_one()

        :param dict notification_data: The notification data sent by the provider
        :return: None
        :raise: ValidationError if inconsistent data were received
        """
        super()._process_notification_data(notification_data)
        if self.provider_code != "moka":
            return

        self.operation = "online_redirect"
        self.moka_tx_code = notification_data.get("trxCode")

        result_code = notification_data.get("resultCode")
        if result_code:
            _logger.warning(
                "the transaction with reference %s underwent an error. reason: %s",
                self.reference,
                result_code,
            )
            self._set_error(_(MOKA_3D_ERRORS.get(result_code, result_code)))
        else:
            self._set_done()

    def _get_tx_from_notification_data(self, provider_code, notification_data):
        """Override of payment to find the transaction based on Moka data.

        :param str provider_code: The code of the provider that handled the transaction
        :param dict notification_data: The notification data sent by the provider
        :return: The transaction if found
        :rtype: recordset of `payment.transaction`
        :raise: ValidationError if inconsistent data were received
        :raise: ValidationError if the data match no transaction
        """
        tx = super()._get_tx_from_notification_data(provider_code, notification_data)
        if provider_code != "moka" or len(tx) == 1:
            return tx

        tx_code = notification_data.get("trxCode")
        if not tx_code:
            raise ValidationError(
                _("Moka: Received data with missing transaction code.")
            )

        tx_hash = notification_data.get("hashValue")
        if not tx_hash:
            raise ValidationError(_("Moka: Received data with missing hash."))

        tx = self.search(
            [
                "|",
                ("moka_success_hash", "=", tx_hash),
                ("moka_fail_hash", "=", tx_hash),
                ("provider_code", "=", "moka"),
            ]
        )

        if not tx:
            raise ValidationError(
                _("Moka: No transaction found matching reference %s.", tx_code)
            )
        return tx
