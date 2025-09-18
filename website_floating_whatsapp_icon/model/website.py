#############################################################################
#
#    Cybrosys Technologies Pvt. Ltd.
#
#    Copyright (C) 2020-TODAY Cybrosys Technologies(<https://www.cybrosys.com>)
#    Author: Noorjahan N A (<https://www.cybrosys.com>)
#
#    You can modify it under the terms of the GNU LESSER
#    GENERAL PUBLIC LICENSE (LGPL v3), Version 3.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU LESSER GENERAL PUBLIC LICENSE (LGPL v3) for more details.
#
#    You should have received a copy of the GNU LESSER GENERAL PUBLIC LICENSE
#    (LGPL v3) along with this program.
#    If not, see <http://www.gnu.org/licenses/>.
#
#############################################################################

import urllib

from odoo import fields, models


class Website(models.Model):
    _inherit = "website"

    mobile_number = fields.Char(translate=True)
    pre_filled_message = fields.Char(
        translate=True, string="WhatsApp Pre-filled Message"
    )

    def get_whatsapp_url(self):
        self.ensure_one()
        if self.mobile_number:
            number = self.mobile_number
            message = self.pre_filled_message or ""
            encoded_message = urllib.parse.quote(message)
            return (
                f"https://api.whatsapp.com/send?phone={number}&text={encoded_message}"
            )
        return ""
