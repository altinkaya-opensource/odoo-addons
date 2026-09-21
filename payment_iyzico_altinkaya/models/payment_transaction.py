# Copyright 2025 Ahmet Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
import logging
from datetime import timedelta

import requests

from odoo import _, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.payment import utils as payment_utils

from ..const import (
    FRAUD_REJECTED,
    FRAUD_UNDER_REVIEW,
    PENDING_CURSOR_PARAM,
    PENDING_MAX_AGE_DAYS,
)
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

    def _iyzico_set_unconfirmed(self, state_message):
        """Park the transaction without telling the customer the order is placed.

        `_set_pending` cannot be used here: `sale` overrides it to mark the
        quotation as sent and to email the order confirmation, and neither is
        true while we do not know whether the card was charged. Going straight
        to `_update_state` keeps the state, the message and the chatter entry
        without those side effects.

        :param str state_message: The reason the outcome is unknown.
        :return: The updated transactions.
        :rtype: recordset of `payment.transaction`
        """
        txs_to_process = self._update_state(("draft",), "pending", state_message)
        txs_to_process._log_received_message()
        return txs_to_process

    def _iyzico_finalize_payment(self, status, response):
        """Finalize the payment based on status and response.

        :param str status: Payment status ('success', 'error' or 'unknown').
        :param response: Response data from iyzico, or an error message.
        :return: None
        """
        try:
            if status == "success":
                fraud_status = response.get("fraudStatus")
                if fraud_status == FRAUD_UNDER_REVIEW:
                    # Charged, but iyzico's fraud team is still reviewing it
                    # and may refund it. Do not confirm the order yet; the
                    # reconciliation cron settles it once they decide.
                    self._iyzico_set_unconfirmed(
                        _("The payment is being reviewed. We will confirm it shortly.")
                    )
                    return
                if fraud_status == FRAUD_REJECTED:
                    self._set_error(
                        _("iyzico refused this payment after a fraud review.")
                    )
                    return

                self._set_done()
                # When setting iyzico amounts, there could be mismatch in amounts
                # due to installment fees. So, firstly confirm the order to lock the
                # amount, then set the amounts from iyzico response.
                # Captured card payments do not consume customer credit. This
                # direct path needs the same risk context as _reconcile_after_done.
                self.with_context(bypass_risk=True)._check_amount_and_confirm_order()
                self._iyzico_set_amounts(response)
            elif status == "unknown":
                # iyzico never confirmed the outcome, so the card may already
                # be charged. Park the transaction instead of failing it; the
                # reconciliation cron asks iyzico for the real state.
                self._iyzico_set_unconfirmed(
                    _(
                        "Waiting for iyzico to confirm the payment. You will be "
                        "notified once the result is known."
                    )
                )
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

        payment_id = str(notification_data.get("paymentId") or "")
        if self.state == "pending":
            # The public callback must not replace the payment we already know,
            # including when it reports failure or the non-3DS response was lost.
            if (
                self.provider_reference
                and payment_id
                and payment_id != self.provider_reference
            ):
                _logger.warning(
                    "iyzico: ignoring a different payment for %s", self.reference
                )
                return
            self._iyzico_resolve_pending()
            return

        self.operation = "online_redirect"
        if notification_data.get("status") == "success":
            connector = iyzicoConnector(
                api_key=self.provider_id.iyzico_api_key,
                secret_key=self.provider_id.iyzico_secret_key,
                base_url=self.provider_id._iyzico_get_api_url(),
                tx=self,
            )
            expected_payment_id = self.provider_reference
            if not expected_payment_id:
                # Legacy initializations did not save paymentId. Establish the
                # binding through the original request before authorizing it.
                detail = connector.retrieve_payment(conversation_id=self.reference)
                if detail.get("status") == "success":
                    expected_payment_id = str(detail.get("paymentId") or "")
            if not payment_id or payment_id != expected_payment_id:
                raise ValidationError(
                    _("iyzico: The payment does not match this transaction.")
                )
            self.provider_reference = payment_id
            status, payload = connector.auth_3ds_response(notification_data)
            self._iyzico_finalize_payment(status, payload)

        else:
            self._set_error(
                _("3DS: Something went wrong during the payment. Please try again.")
            )

    def _cron_iyzico_resolve_pending(self, batch_size=100):
        """Resolve the transactions iyzico never confirmed.

        A payment whose authorization ends in a network failure is left
        pending: iyzico may or may not have charged the card. Ask iyzico for
        the real state of each one and finalize it.

        :param int batch_size: The maximum number of transactions per run.
        :return: None
        """
        cutoff = fields.Datetime.now() - timedelta(days=PENDING_MAX_AGE_DAYS)
        stale_txs = self.search(
            [
                ("provider_code", "=", "iyzico_altinkaya"),
                ("state", "=", "pending"),
                ("create_date", "<=", cutoff),
            ]
        )
        if stale_txs:
            _logger.warning(
                "iyzico: %s transaction(s) unconfirmed for over %s days, check them "
                "by hand: %s",
                len(stale_txs),
                PENDING_MAX_AGE_DAYS,
                ", ".join(stale_txs.mapped("reference")),
            )

        config = self.env["ir.config_parameter"].sudo()
        last_id = int(config.get_param(PENDING_CURSOR_PARAM, "0"))
        domain = [
            ("provider_code", "=", "iyzico_altinkaya"),
            ("state", "=", "pending"),
            ("create_date", ">", cutoff),
        ]
        pending_txs = self.search(
            domain + [("id", ">", last_id)],
            order="id asc",
            limit=batch_size,
        )
        remaining = batch_size - len(pending_txs)
        if remaining:
            # Fill spare capacity from the beginning, even when new payments
            # keep arriving. The disjoint ID ranges visit each record once.
            pending_txs += self.search(
                domain + [("id", "<=", last_id)],
                order="id asc",
                limit=remaining,
            )
        for tx in pending_txs:
            try:
                # A savepoint per transaction: one failure must not undo the
                # ones already resolved in this run.
                with self.env.cr.savepoint():
                    tx._iyzico_resolve_pending()
            except Exception:
                _logger.exception(
                    "iyzico: could not resolve pending transaction %s", tx.reference
                )
        if pending_txs:
            # Advance outside the savepoints even if a record could not be
            # resolved, retaining the order of the circular batch.
            config.set_param(PENDING_CURSOR_PARAM, pending_txs[-1].id)

    def _iyzico_resolve_pending(self):
        """Ask iyzico for the real state of one unconfirmed transaction.

        Note: self.ensure_one()

        :return: None
        """
        self.ensure_one()
        connector = iyzicoConnector(
            api_key=self.provider_id.iyzico_api_key,
            secret_key=self.provider_id.iyzico_secret_key,
            base_url=self.provider_id._iyzico_get_api_url(),
            tx=self,
        )
        try:
            # A stored ID may originate from an old unsigned callback. Only
            # the original, server-generated reference selects this payment.
            detail = connector.retrieve_payment(conversation_id=self.reference)
        except requests.RequestException:
            # iyzico is still unreachable; the next run tries again.
            _logger.warning("iyzico: %s still unconfirmed", self.reference)
            return

        if detail.get("status") != "success":
            # The query itself failed, for instance because iyzico refused the
            # credentials. That says nothing about the charge, so the
            # transaction stays pending and the next run asks again.
            _logger.warning(
                "iyzico: cannot read the state of %s: (%s) %s",
                self.reference,
                detail.get("errorCode"),
                detail.get("errorMessage"),
            )
            return

        # The charge may have been made without us ever learning its id.
        payment_id = str(detail.get("paymentId") or "")
        if not payment_id or (
            self.provider_reference and self.provider_reference != payment_id
        ):
            _logger.warning("iyzico: payment identity mismatch for %s", self.reference)
            return
        if not self.provider_reference:
            self.provider_reference = payment_id

        payment_status = detail.get("paymentStatus")
        if payment_status == "SUCCESS":
            self._iyzico_finalize_payment("success", detail)
        elif payment_status == "FAILURE":
            self._iyzico_finalize_payment(
                "error", f"({detail.get('errorCode')}) {detail.get('errorMessage')}"
            )
        else:
            # Still in progress on iyzico's side, for instance a 3DS callback
            # they never authorized. The next run checks again.
            _logger.info(
                "iyzico: %s is still in progress (%s)", self.reference, payment_status
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
