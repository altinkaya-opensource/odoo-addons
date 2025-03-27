# Copyright 2022 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

# Copyright 2024 Ismail Cagan Yilmaz (https://github.com/milleniumkid)
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

from odoo import api, fields, models


class CRMClaimMapping(models.AbstractModel):
    _name = "crm.claim.mapping"
    _description = "Base model for CRM Claim - Odoo models integration"

    crm_claim_ids = fields.Many2many("crm.claim", string="Claims")
    crm_claim_count = fields.Integer(
        compute="_compute_claims_count",
        store=True,
        default=0,
        string="Claim Count",
    )

    @api.depends("crm_claim_ids")
    def _compute_claims_count(self):
        for rec in self:
            rec.crm_claim_count = len(rec.crm_claim_ids) if rec.crm_claim_ids else 0

    def action_view_claims(self):
        claims = self.mapped("crm_claim_ids")
        action = self.env.ref("crm_claim.crm_claim_category_claim0").read()[0]
        form_view = [(self.env.ref("crm_claim.crm_case_claims_form_view").id, "form")]
        if len(claims) > 1:
            action["domain"] = [("id", "in", claims.ids)]
            return action

        else:
            if "views" in action:
                action["views"] = form_view + [
                    (state, view) for state, view in action["views"] if view != "form"
                ]
            else:
                action["views"] = form_view

            if claims:
                action["res_id"] = claims.ids[0]
            else:
                action["context"] = self._prepare_claim_context()

        return action

    def _prepare_claim_context(self):
        vals = {"default_model_ref_id": f"{self._name},{self.id}"}

        if self._name == "sale.order":
            sale_order = self

        elif self._name == "account.move":
            sale_order = (
                fields.first(self.mapped("move_line_ids.sale_line_ids.order_id"))
                or False
            )

        elif self._name == "stock.picking":
            sale_order = (
                fields.first(self.mapped("move_ids.sale_line_id.order_id"))
                or False
            )

        else:
            sale_order = False

        if sale_order:
            vals.update(
                {
                    "default_partner_id": sale_order.partner_id.id or False,
                    "default_partner_phone": sale_order.partner_id.phone or False,
                    "default_email_from": sale_order.partner_id.email or False,
                    "default_user_id": sale_order.create_uid.id or False,
                    "default_team_id": sale_order.team_id.id or False,
                    "default_source_id": sale_order.source_id.id or False,
                    "default_carrier_id": sale_order.carrier_id.id or False,
                }
            )
        return vals


class CRMClaimSaleOrderMixin(models.Model):
    _name = "sale.order"
    _inherit = ["sale.order", "crm.claim.mapping"]


class CRMClaimMoveMixin(models.Model):
    _name = "account.move"
    _inherit = ["account.move", "crm.claim.mapping"]


class CRMClaimPickingMixin(models.Model):
    _name = "stock.picking"
    _inherit = ["stock.picking", "crm.claim.mapping"]


class CRMClaimProductMixin(models.Model):
    _name = "product.product"
    _inherit = ["product.product", "crm.claim.mapping"]
