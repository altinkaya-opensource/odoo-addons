# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Classify stored refund rows without changing their accounting links."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["hepsiburada.settlement"].search(
        [("hb_transaction_type", "in", ("CommissionRefund", "CommissionInvoiceRefund"))]
    ).write({"transaction_type": "commission_refund"})
