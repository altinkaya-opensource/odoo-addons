# Copyright 2022 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from datetime import datetime, timedelta

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError

FINEKRA_ENDPOINT = "https://polynom-api.finekra.com"


class OnlineBankStatementProviderFinekra(models.Model):
    _inherit = "online.bank.statement.provider"

    finekra_email = fields.Char("Finekra App Key")
    finekra_password = fields.Char("Finekra App Secret")
    finekra_tenant_code = fields.Text("Finekra Tenant code")
    finekra_jwt_token = fields.Text("JWT Token", readonly=True)
    finekra_token_interval = fields.Datetime(
        "Token Interval", default="2000-01-01 00:00:00"
    )

    @api.model
    def _get_available_services(self):
        return super()._get_available_services() + [
            ("finekra", "Finekra"),
        ]

    def _obtain_statement_data(self, date_since, date_until):
        self.ensure_one()
        if self.service != "finekra":
            return super()._obtain_statement_data(
                date_since,
                date_until,
            )
        return self._finekra_obtain_statement_data(date_since, date_until)

    ##########
    # finekra #
    ##########

    def _finekra_get_request(self, endpoint, data=None):
        """
        Sends GET request to finekra Endpoint
        :param endpoint:
        :param data:
        :return:
        """
        headers = {
            "Content-Type": (
                "application/json;odata.metadata=minimal;odata.streaming=true"
            ),
            "Authorization": f"Bearer {self.finekra_jwt_token}",
        }
        response = requests.get(endpoint, params=data, headers=headers, timeout=10)

        if response.status_code == 200:
            return response.json()
        else:
            raise UserError(
                _(
                    "Finekra API returned an error: %(resp_content)d",
                    resp_content=response.content,
                ),
            )

    def _finekra_post_request(self, endpoint, data=None):
        """
        Sends POST request to finekra Endpoint
        :param endpoint:
        :param data:
        :return:
        """
        headers = {
            "Content-Type": (
                "application/json;odata.metadata=minimal;odata.streaming=true"
            ),
            "Authorization": f"Bearer {self.finekra_jwt_token}",
        }
        response = requests.post(endpoint, json=data, headers=headers, timeout=10)

        if response.status_code == 200:
            return response.json()
        else:
            raise UserError(_("Finekra API Error."))

    def _finekra_get_auth(self):
        self.ensure_one()
        if self.finekra_email and self.finekra_password and self.finekra_tenant_code:
            if (
                not self.finekra_jwt_token
                or self.finekra_token_interval < datetime.now()
            ):
                vals = {
                    "email": self.finekra_email,
                    "password": self.finekra_password,
                    "tenantCode": self.finekra_tenant_code,
                    "screenOption": 0,
                }
                resp = requests.post(
                    f"{FINEKRA_ENDPOINT}/api/Auth/DealerLogin", json=vals, timeout=10
                ).json()
                if resp.get("success"):
                    self.write(
                        {
                            "finekra_jwt_token": resp["data"].get("token"),
                            "finekra_token_interval": datetime.now()
                            + timedelta(days=1),
                        }
                    )
        else:
            raise UserError(_("Please fill email, password and tenant code."))

    def _finekra_get_transaction(self, account_id, date_since, date_until):
        page_url = f"{FINEKRA_ENDPOINT}/api/AccountTransaction"

        vals = {
            "$filter": f"TenantAccountId eq {account_id} and"
            f" date(TransactionDateValue) le {date_until.strftime('%Y-%m-%d')} and"
            f" date(TransactionDateValue) ge {date_since.strftime('%Y-%m-%d')}"
        }

        data = self._finekra_get_request(endpoint=page_url, data=vals)
        if data.get("value"):
            return data.get("value")
        else:
            return []

    def _finekra_date_from_string(self, date_str):
        """Finekra dates are GMT+3, so we don't need to convert them to UTC"""
        dt = datetime.strptime(date_str, "%d.%m.%Y %H:%M")
        return dt

    def _finekra_obtain_statement_data(self, date_since, date_until):
        self.ensure_one()
        self._finekra_get_auth()
        journal = self.journal_id
        account_id = journal.finekra_account_id

        if not account_id:
            raise UserError(
                _("finekra : wrong configuration, unknown account %s")
                % journal.bank_account_id.acc_number
            )
        transaction_lines = self._finekra_get_transaction(
            account_id, date_since, date_until
        )
        new_transactions = []
        # transcationun currency si, unique import idsi, amount'u
        sequence = 0
        for transaction in transaction_lines:
            # currency = transaction.get('currency')
            sequence += 1
            date = self._finekra_date_from_string(transaction.get("transactionDate"))
            vals_line = {
                "sequence": sequence,
                "date": date,
                "name": transaction.get("description", journal.name),
                "unique_import_id": transaction["id"],
                "amount": transaction["amountForExcel"],
            }
            # if currency != 'TRY':
            #     vals_line.update({
            #         'currency_id': currency_dict.get(currency),
            #     })

            new_transactions.append(vals_line)
        if new_transactions:
            return new_transactions, {}
        return
