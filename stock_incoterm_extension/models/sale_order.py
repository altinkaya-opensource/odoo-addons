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
from odoo.tools.translate import _


class SaleOrder(models.Model):
    _inherit = "sale.order"

    req_destination_port = fields.Boolean(
        string="Requires destination port", related="incoterm.destination_port"
    )
    req_transport_type = fields.Boolean(
        string="Requires transport type", related="incoterm.transport_type"
    )
    destination_port = fields.Char(string="Destination port")
    transport_type = fields.Selection(
        selection=[
            ("0", _("Transport mode not specified")),
            ("1", _("Maritime transport")),
            ("2", _("Rail transport")),
            ("3", _("Road transport")),
            ("4", _("Air transport")),
            ("5", _("Mail")),
            ("6", _("Multimodal transport")),
            ("7", _("Fixed transport installations")),
            ("8", _("Inland water transport")),
            ("9", _("Transport mode not applicable")),
        ],
        string="Transport type",
    )

    @api.model
    def _prepare_invoice(self):
        res = super()._prepare_invoice()
        res.update(
            {
                "incoterm": self.incoterm.id,
                "destination_port": self.destination_port,
                "transport_type": self.transport_type,
            }
        )
        return res
