# Copyright 2024 Ahmet Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
import re

from odoo import fields, models


class ResBank(models.Model):
    _inherit = "res.bank"

    fax = fields.Char()

    def _display_address(self):
        """
        This method was missing in the original res.bank model.
        """

        # get the information that will be injected into the display format
        # get the address format

        address_format = (
            "%(street)s %(street2)s %(city)s %(state_name)s %(zip)s %(country_name)s"
        )
        args = {
            "street": self.street or "",
            "street2": self.street2 or "",
            "city": self.city or "",
            "state_name": self.state.name or "",
            "zip": self.zip or "",
            "country_name": self.country.name or "",
        }

        display_address = address_format % args
        display_address = re.sub("\n[\s,]*\n+", "\n", display_address.strip())
        return re.sub(r"^\s+", "", display_address, flags=re.M)
