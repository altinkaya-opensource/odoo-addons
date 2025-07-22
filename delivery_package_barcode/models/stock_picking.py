# Copyright 2025 Yiğit Budak (https://github.com/yibudak).
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo import _, fields, models
from odoo.exceptions import ValidationError


class StockPicking(models.Model):
    _inherit = "stock.picking"
    is_packaged = fields.Boolean(string="Is packaged", default=False)

    block_autoinvoicing = fields.Boolean(
        compute="_compute_block_autoinvoicing",
        search="_search_block_autoinvoicing",
        help="If True, the autoinvoicing will be blocked for this picking.",
    )

    def _block_autoinvoicing_domain(self):
        return [
            "|",
            ("partner_id.commercial_partner_id.block_autoinvoicing", "=", True),
            ("sale_id.block_autoinvoicing", "=", True),
        ]

    def _compute_block_autoinvoicing(self):
        for picking in self:
            picking.block_autoinvoicing = (
                picking.partner_id.commercial_partner_id.block_autoinvoicing
                or picking.sale_id.block_autoinvoicing
            )

    def _search_block_autoinvoicing(self, operator, value):
        if operator not in ("=", "!="):
            raise ValidationError(
                _("Unsupported operator for Block Autoinvoicing search")
            )
        domain = self._block_autoinvoicing_domain()
        if (operator == "=" and value) or (operator == "!=" and not value):
            return domain
        else:
            return ["!", *domain]
