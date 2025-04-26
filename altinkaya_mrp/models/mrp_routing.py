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
from odoo import _, fields, models


class MrpRouting(models.Model):
    """Specifies routings of work centers"""

    _name = "mrp.routing"
    _description = "Routings"

    name = fields.Char("Routing", required=True)
    active = fields.Boolean(
        default=True,
        help="If the active field is set to False, it will allow you to hide the "
        "routing without removing it.",
    )
    code = fields.Char(
        "Reference", copy=False, default=lambda self: _("New"), readonly=True
    )
    note = fields.Text("Description")
    location_id = fields.Many2one(
        "stock.location",
        "Raw Materials Location",
        help="Keep empty if you produce at the location where you find the "
        "raw materials. Set a location if you produce at a fixed location. "
        "This can be a partner location if you subcontract the "
        "manufacturing operations.",
    )
