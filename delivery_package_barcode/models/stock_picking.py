# Copyright 2025 Yiğit Budak, Ümithan Güldemir (https://github.com/yibudak) (https://github.com/umithan-guldemir)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo import fields, models


class StockPicking(models.Model):
    _inherit = "stock.picking"
    is_packaged = fields.Boolean(string="Is packaged", default=False)

    block_autoinvoicing = fields.Boolean(
        compute="_compute_block_autoinvoicing",
        help="If True, the autoinvoicing will be blocked for this picking.",
    )

    def _compute_block_autoinvoicing(self):
        for record in self:
            commercial_partner = record.partner_id.commercial_partner_id
            sale_id = record.sale_id
            if commercial_partner.block_autoinvoicing or sale_id.block_autoinvoicing:
                record.block_autoinvoicing = True
            else:
                record.block_autoinvoicing = False
