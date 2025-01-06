# Copyright 2023 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo import models, api


class DeliverySendBatchEmail(models.TransientModel):
    _name = "delivery.send.batch.email"
    _description = "Send Batch Email to Customers"

    # @api.multi
    def send_batch_email(self):
        context = dict(self._context or {})
        active_ids = context.get("active_ids", []) or []
        pickings = self.env["stock.picking"].browse(active_ids)
        for record in self.web_progress_iter(
            pickings.filtered(lambda p: not p.mail_sent and p.shipping_number),
            msg="Sending emails...",
        ):
            record.button_mail_send()
            self.env.cr.commit()
        return {"type": "ir.actions.act_window_close"}
