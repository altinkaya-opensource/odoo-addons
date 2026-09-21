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

PROD_URL = "https://api.iyzipay.com"
TEST_URL = "https://sandbox-api.iyzipay.com"

# iyzico periodically becomes unreachable: their API resets the connection
# while they are under attack. A reset is no proof that the request was not
# processed, so only calls that cannot move money are retried. See
# `iyzicoConnector._request`.
REQUEST_TIMEOUT = 30
RETRY_COUNT = 2
RETRY_BACKOFF = 0.5

# iyzico's fraud review, as documented under "Fraud Bildirimleri". 0 means
# their fraud team is still looking at the charge and delivery must be
# withheld; -1 means they rejected it after the review and refunded the card.
# 1 and 2 are the two approved outcomes.
FRAUD_UNDER_REVIEW = 0
FRAUD_REJECTED = -1

# How far back the reconciliation cron looks. Older unconfirmed transactions
# are reported instead, because they need someone to look at them.
PENDING_MAX_AGE_DAYS = 7
PENDING_CURSOR_PARAM = "payment_iyzico_altinkaya.pending_cursor"
