# Copyright 2025 Ismail Cagan Yilmaz (https://github.com/milleniumkid)
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

from odoo import models


class PaymentTransaction(models.Model):
    _inherit = "payment.transaction"

    def _post_process_after_done(self):
        res = super()._get_post_processing_values()
        for tx in self.filtered(lambda t: t.sale_order_ids and t.payment_id):
            tx.sale_order_ids.payment_ids = [(4, tx.payment_id.id)]
            tx.sale_order_ids._compute_payment_state()
        return res
