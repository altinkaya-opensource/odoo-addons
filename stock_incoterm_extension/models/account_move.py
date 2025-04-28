##############################################################################
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

from odoo import api, fields, models


class AccountMove(models.Model):
    _inherit = "account.move"

    @api.model
    def _get_selection_transport_type(self):
        return self.env["sale.order"].fields_get(allfields=["transport_type"])[
            "transport_type"
        ]["selection"]

    req_destination_port = fields.Boolean(
        string="Requires destination port",
        related="invoice_incoterm_id.destination_port",
    )
    req_transport_type = fields.Boolean(
        string="Requires transport type", related="invoice_incoterm_id.transport_type"
    )
    destination_port = fields.Char(string="Destination port")
    transport_type = fields.Selection(
        selection="_get_selection_transport_type", string="Transport type"
    )
