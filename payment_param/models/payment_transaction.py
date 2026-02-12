# Copyright 2022 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
import logging

from odoo import _, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.payment import utils as payment_utils

_logger = logging.getLogger(__name__)


class PaymentTransaction(models.Model):
    _inherit = "payment.transaction"

    param_islem_id = fields.Char(readonly=True, copy=False)
    param_islem_guid = fields.Char(sreadonly=True, copy=False)
    param_islem_hash = fields.Char(readonly=True, copy=False)
    param_islem_tarihi = fields.Char(readonly=True, copy=False)
    param_dekont_id = fields.Char(readonly=True, copy=False)
    param_kk_no = fields.Char(readonly=True, copy=False)
    param_tahsilat_tutari = fields.Char(readonly=True, copy=False)

    # === BUSINESS METHODS ===#

    def _get_specific_processing_values(self, processing_values):
        """Override of payment to return  Moka-specific processing values.

        Note: self.ensure_one() from `_get_processing_values`

        :param dict processing_values: The generic processing values of the transaction
        :return: The dict of provider-specific processing values
        :rtype: dict
        """
        res = super()._get_specific_processing_values(processing_values)
        if self.provider_code != "param":
            return res

        return {
            "access_token": payment_utils.generate_access_token(
                processing_values["reference"],
                processing_values["amount"],
                processing_values["partner_id"],
            )
        }

    def _process_notification_data(self, notification_data):
        """Override of payment to process the transaction based on Moka data.

        Note: self.ensure_one()

        :param dict notification_data: The notification data sent by the provider
        :return: None
        :raise: ValidationError if inconsistent data were received
        """
        super()._process_notification_data(notification_data)
        if self.provider_code != "param":
            return

        self.operation = "online_redirect"
        self.write(
            {
                "param_islem_guid": notification_data.get("TURKPOS_RETVAL_GUID"),
                "param_islem_hash": notification_data.get("TURKPOS_RETVAL_Hash"),
                "param_islem_tarihi": notification_data.get(
                    "TURKPOS_RETVAL_Islem_Tarihi"
                ),
                "param_dekont_id": notification_data.get("TURKPOS_RETVAL_Dekont_ID"),
                "param_kk_no": notification_data.get("TURKPOS_RETVAL_KK_No"),
                "param_tahsilat_tutari": notification_data.get(
                    "TURKPOS_RETVAL_Tahsilat_Tutari"
                ),
            }
        )

        result_code = notification_data.get("TURKPOS_RETVAL_Sonuc")
        if result_code != "1":
            error_str = notification_data.get("TURKPOS_RETVAL_Sonuc_Str")
            _logger.warning(
                "the transaction with reference %s underwent an error. reason: %s",
                self.reference,
                error_str,
            )
            self._set_error(error_str)
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
        if provider_code != "param" or len(tx) == 1:
            return tx

        tx_code = notification_data.get("TURKPOS_RETVAL_Siparis_ID")
        if not tx_code:
            raise ValidationError(
                _("Param: Received data with missing transaction code.")
            )

        tx_param_id = notification_data.get("TURKPOS_RETVAL_SanalPOS_Islem_ID")
        if not tx_param_id:
            raise ValidationError(_("Param: Received data with missing hash."))

        tx = self.search(
            [
                ("reference", "=", tx_code),
                ("param_islem_id", "=", tx_param_id),
                ("provider_code", "=", "param"),
            ]
        )

        if not tx:
            raise ValidationError(
                _(
                    "Param: No transaction found matching reference %(tx_code)s.",
                    tx_code=tx_code,
                )
            )
        return tx
