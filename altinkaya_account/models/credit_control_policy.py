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
from odoo import fields, models
from odoo.osv import expression
from odoo.tools.safe_eval import safe_eval


class CreditControlPolicy(models.Model):
    _inherit = "credit.control.policy"

    move_line_domain = fields.Char(
        string="Additional Move Line Domain",
        help="Additional domain to filter move lines for credit control checks. "
        "This domain is added to the default domain used to select move lines.",
        default="[]",
    )

    def _move_lines_domain(self, credit_control_run):
        """
        Extend the move lines domain with the additional domain defined
        in the 'move_line_domain' field.
        """
        res = super()._move_lines_domain(credit_control_run)
        for policy in self:
            if policy.move_line_domain:
                domain = safe_eval(policy.move_line_domain)
                res = expression.AND([res, domain])
        return res
