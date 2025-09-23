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


import logging

from odoo import _, http
from odoo.exceptions import ValidationError
from odoo.http import request

_logger = logging.getLogger(__name__)

_IYZICO_PROCESS_URL = "/payment/iyzico/payments"
_IYZICO_RETURN_URL = "/payment/iyzico/return"
_IYZICO_INSTALLMENT_OPTIONS_URL = "/payment/iyzico/installment_options"


class iyzicoCoontroller(http.Controller):
    @http.route(_IYZICO_INSTALLMENT_OPTIONS_URL, type="json", auth="public")
    def iyzico_installment_options(
        self, card_number, amount, access_token, partner_id, provider_id
    ):
        """Fetch installment options for a given card number and amount.

        :param str card_number: The card number to fetch installment options for.
        :param float amount: The amount of the transaction.
        :param str access_token: The access token used to verify the provided values.
        :param int partner_id: The partner ID.
        :param int provider_id: The provider handling the transaction.
        :return: The JSON-formatted content of the response.
        :rtype: dict
        """
        response = {"status": "", "installment_options": []}

        order = request.env["sale.order"].search(
            [("access_token", "=", access_token), ("partner_id", "=", partner_id)],
            limit=1,
        )
        provider_sudo = (
            request.env["payment.provider"].sudo().browse(provider_id).exists()
        )
        try:
            order.ensure_one()
            installment_options = provider_sudo.iyzico_check_installment(
                card_number,
                amount,
                order,
                request.env["payment.transaction"],  # dummy recordset
            )
            response["status"] = "success"
            response["installment_options"] = installment_options
        except ValueError:  # Like if order is not found
            response["status"] = "error"
            response["error_message"] = _("Invalid response.")
        except Exception as exc:
            _logger.error("[iyzico] Error while fetching installment options: %s", exc)
            response["status"] = "error"
            response["error_message"] = _("An error occurred. Please try again.")

        return response

    @http.route(_IYZICO_PROCESS_URL, type="json", auth="public")
    def iyzico_payments(
        self,
        provider_id,
        reference,
        access_token,
        installment,
        card_args,
        force_3ds=False,
    ):
        """Make a payment request and handle the notification data.

        :param int provider_id: The provider handling the transaction.
        :param str reference: The reference of the transaction.
        :param str access_token: The access token used to verify the provided values.
        :param int installment: The installment number.
        :param dict card_args: The card information arguments.
        :param bool force_3ds: Whether to force 3DS authentication.
        :return: The JSON-formatted content of the response.
        :rtype: dict
        """
        # Check that the transaction details have not been altered.
        # This allows preventing users
        # from validating transactions by paying less than agreed upon.
        response = {
            "status": "",
            "checkout_form_script": "",
        }
        provider_sudo = (
            request.env["payment.provider"].sudo().browse(provider_id).exists()
        )
        tx_sudo = (
            request.env["payment.transaction"]
            .sudo()
            .search([("reference", "=", reference)])
        )
        try:
            # 1. Ensure that we have a transaction matching the reference
            tx_sudo._iyzico_ensure_access_token(access_token)

            # 2. Ensure user input is valid
            card_error = provider_sudo._iyzico_validate_card_args(card_args)
            if card_error:
                raise ValidationError(card_error)

            payment_method, gateway_response = provider_sudo._iyzico_initialize_payment(
                tx_sudo, card_args, installment, force_3ds=force_3ds
            )

            if payment_method == "non_3ds":
                # Finalize the payment immediately in case of non-3DS payment
                tx_sudo._iyzico_finalize_payment(*gateway_response)

            response["status"] = "success"
            response["payment_method"] = payment_method
            response["gateway_response"] = gateway_response

        except AssertionError:  # When access token is invalid
            response["status"] = "error"
            response["error_message"] = _("iyzico: Invalid access token.")
        except ValueError:  # Like if tx_sudo is not found
            response["status"] = "error"
            response["error_message"] = _("Invalid response.")
        except ValidationError as exc:
            tx_sudo._set_error(str(exc))
            response["status"] = "error"
            response["error_message"] = str(exc)
        except Exception as exc:
            _logger.error("[iyzico] Validation error: %s", exc)
            response["status"] = "error"
            error_msg = _("Something bad happened. Please try again.")
            response["error_message"] = error_msg

        return response

    @http.route(
        _IYZICO_RETURN_URL,
        type="http",
        auth="public",
        csrf=False,
        save_session=False,
        methods=["POST"],
    )
    def iyzico_return_from_3ds_auth(self, **kwargs):
        """Handle the return from the 3DS authentication.

        :param dict kwargs: Notification data from Iyzico.
        :return: Redirect response to status page.
        :rtype: werkzeug.wrappers.Response
        """
        request.env["payment.transaction"].sudo()._handle_notification_data(
            "iyzico_altinkaya", kwargs
        )

        # Redirect the user to the status page
        return request.redirect("/payment/status")
