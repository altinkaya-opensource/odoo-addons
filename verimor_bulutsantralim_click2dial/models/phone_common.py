# Copyright 2022 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

# Copyright 2024 Ismail Cagan Yilmaz (https://github.com/milleniumkid)
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

import logging

from odoo import _, api, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)
try:
    import phonenumbers

    _sms_phonenumbers_lib_imported = True

except ImportError:
    _sms_phonenumbers_lib_imported = False
    _logger.info(
        "The `phonenumbers` Python module is not available. "
        "Phone number validation will be skipped. "
        "Try `pip3 install phonenumbers` to install it."
    )


class PhoneCommon(models.AbstractModel):
    _inherit = "phone.common"

    def _phone_get_country(self, partner):
        if "country_id" in partner:
            return partner.country_id
        return self.env.company.country_id

    def _number_sanitization(self, erp_number):
        ctx = self.env.context.copy()
        if (
            ctx.get("click2dial_model") == "res.partner"
            and ctx.get("click2dial_id")
            and _sms_phonenumbers_lib_imported
        ):
            partner = self.env["res.partner"].browse(ctx.get("click2dial_id"))
            country = self._phone_get_country(partner)
            country_code = country.code if country else None
            try:
                phone_nbr = phonenumbers.parse(
                    erp_number, region=country_code, keep_raw_input=True
                )
            except phonenumbers.phonenumberutil.NumberParseException:
                return erp_number
            if not phonenumbers.is_possible_number(
                phone_nbr
            ) or not phonenumbers.is_valid_number(phone_nbr):
                return erp_number
            phone_fmt = phonenumbers.PhoneNumberFormat.E164
            return phonenumbers.format_number(phone_nbr, phone_fmt)
        else:
            return erp_number

    @api.model
    def click2dial(self, erp_number):
        res = super().click2dial(erp_number)
        if not erp_number:
            raise UserError(_("Missing phone number"))

        bulutsantralim_connector = self.env.company.bulutsantralim_connector_id

        if bulutsantralim_connector:
            caller = (
                self.env.user.internal_number.split(",")[0]
                if self.env.user.internal_number
                else False
            )
            number = self._number_sanitization(erp_number)

            if not caller:
                raise UserError(_("Missing internal number"))

            bulutsantralim_connector._start_call_verimor(number, caller)
            res["dialed_number"] = number

        return res
