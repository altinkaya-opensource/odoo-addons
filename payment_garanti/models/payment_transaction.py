# Copyright 2022 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
import logging

from odoo import _, fields, models
from odoo.exceptions import ValidationError
from odoo.osv import expression

from odoo.addons.payment import utils as payment_utils

from .garanti_connector import GarantiConnector

_logger = logging.getLogger(__name__)


class PaymentTransaction(models.Model):
    _inherit = "payment.transaction"

    garanti_secure3d_hash = fields.Char(
        string="Garanti Secure 3D Hash",
        help="The hash used to authenticate "
        "the transaction with Garanti "
        "Secure 3D",
        readonly=True,
        copy=False,
    )
    garanti_xid = fields.Char(string="Garanti XID", readonly=True, copy=False)
    log_ids = fields.Many2many(
        "ir.logging",
        string="Logs",
        store=False,
        help="Logs related to the transaction",
        compute="_compute_transaction_log_ids",
    )

    def _compute_transaction_log_ids(self):
        for tx in self:
            domain = [("message", "ilike", tx.reference.split("-")[0])]
            if tx.garanti_secure3d_hash:
                domain = expression.OR(
                    [domain, [("message", "ilike", tx.garanti_secure3d_hash)]]
                )
            if tx.garanti_xid:
                domain = expression.OR([domain, [("message", "ilike", tx.garanti_xid)]])

            domain = expression.AND(
                [domain, ["|", ("func", "ilike", "3d"), ("func", "ilike", "garanti")]]
            )

            tx.log_ids = self.env["ir.logging"].search(domain)

    def _set_error(self, state_message):
        # Todo: finish this method
        res = super()._set_error(state_message)
        error_txs = self.filtered(
            lambda t: t.provider_id.code == "garanti" and t.state == "error"
        )
        if error_txs:
            error_message = (
                self.env["payment.provider.error"]
                .sudo()
                .search([("full_message", "=", state_message)], limit=1)
            )
            if error_message and error_message.modified_error_message:
                for tx in error_txs:
                    tx.state_message = error_message.with_context(
                        lang=tx.partner_id.lang or "tr_TR"
                    ).modified_error_message
        return res

    # === BUSINESS METHODS ===#

    def _get_specific_processing_values(self, processing_values):
        """Override of payment to return  Garanti-specific processing values.

        Note: self.ensure_one() from `_get_processing_values`

        :param dict processing_values: The generic processing values of the transaction
        :return: The dict of provider-specific processing values
        :rtype: dict
        """
        res = super()._get_specific_processing_values(processing_values)
        if self.provider_code != "garanti":
            return res

        res.update(
            {
                "access_token": payment_utils.generate_access_token(
                    processing_values["reference"],
                    processing_values["amount"],
                    processing_values["partner_id"],
                )
            }
        )
        return res

    def _process_notification_data(self, notification_data):
        """Override of payment to process the transaction based on Garanti data.

        Note: self.ensure_one()

        :param dict notification_data: The notification data sent by the provider
        :return: None
        :raise: ValidationError if inconsistent data were received
        """
        super()._process_notification_data(notification_data)
        if self.provider_code != "garanti":
            return

        self.provider_id.log_xml(notification_data, "3ds_return")

        self.operation = "online_redirect"
        self.garanti_xid = notification_data.get("xid")
        md_status = notification_data.get("mdstatus")
        error_msg = notification_data.get("mderrormessage")
        if md_status not in ["1", "2", "3", "4", "5"]:
            _logger.warning(
                "the transaction with reference %s underwent an error." " reason: %s",
                self.reference,
                error_msg,
            )
            self._set_error(f"{md_status}: {error_msg}")
        else:
            connector = GarantiConnector(
                self.provider_id,
                self,
                self.amount,
                self.currency_id.id,
            )
            try:
                res = connector._garanti_payment_callback(notification_data)
                if res == "Approved":
                    self._set_done()
                else:
                    self._set_error(res)
            except Exception as e:
                _logger.warning(
                    "Garanti payment callback error: %s, data: %s",
                    (e, notification_data),
                    exc_info=True,
                )
                self._set_error(res)

    def _get_tx_from_notification_data(self, provider_code, notification_data):
        """Override of payment to find the transaction based on Garanti data.

        :param str provider_code: The code of the provider that handled the transaction
        :param dict notification_data: The notification data sent by the provider
        :return: The transaction if found
        :rtype: recordset of `payment.transaction`
        :raise: ValidationError if inconsistent data were received
        :raise: ValidationError if the data match no transaction
        """
        tx = super()._get_tx_from_notification_data(provider_code, notification_data)
        if provider_code != "garanti" or len(tx) == 1:
            return tx

        tx_code = notification_data.get("secure3dhash")
        if not tx_code:
            raise ValidationError(
                _("Garanti: Received data with missing transaction code.")
            )

        tx_ref = notification_data.get("orderid")
        if not tx_ref:
            raise ValidationError(_("Garanti: Received data with missing ref."))

        tx = self.search(
            [
                ("garanti_secure3d_hash", "=", tx_code),
                ("state", "not in", ("done", "cancel", "error")),
            ],
            limit=1,
            order="id desc",
        )

        if not tx:
            raise ValidationError(
                _(
                    "Garanti: No transaction found matching reference %(tx_code)s.",
                    tx_code=tx_code,
                )
            )
        return tx
