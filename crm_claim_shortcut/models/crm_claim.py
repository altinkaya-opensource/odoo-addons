# Copyright 2022 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

# Copyright 2024 Ismail Cagan Yilmaz (https://github.com/milleniumkid)
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

from odoo import api, fields, models

from odoo.addons.crm_claim.models.crm_claim import APPLICABLE_MODELS

APPLICABLE_MODELS.append("stock.picking")  # Add stock.picking to model_ref_id


class CRMClaim(models.Model):
    _inherit = "crm.claim"

    source_id = fields.Many2one("utm.source", string="Source")
    carrier_id = fields.Many2one("delivery.carrier", string="Carrier")

    @api.model_create_multi
    def create(self, vals_list):
        res = super().create(vals_list)
        for rec in res.filtered(lambda x: x.model_ref_id):
            rec.model_ref_id.crm_claim_ids = [(4, rec.id)]
        return res

    def unlink(self):
        for rec in self.filtered(lambda x: x.model_ref_id):
            rec.model_ref_id.crm_claim_ids = [(3, rec.id)]
        return super().unlink()
