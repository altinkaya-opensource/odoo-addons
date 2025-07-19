from odoo import models


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    def action_rfq_send(self):
        """
        Override the action_rfq_send method to set the
        email template based on the state of the purchase order.
        """
        res = super().action_rfq_send()
        try:
            rfq_template_id = self.env.ref("purchase.email_template_edi_purchase").id
            po_template_id = self.env.ref(
                "purchase.email_template_edi_purchase_done"
            ).id
        except ValueError:
            return res

        template_id = (
            po_template_id if self.state in ["purchase", "done"] else rfq_template_id
        )

        context = res.get("context", {})
        context["default_template_id"] = template_id
        res["context"] = context

        return res
