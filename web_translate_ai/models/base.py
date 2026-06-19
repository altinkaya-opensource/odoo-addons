# Copyright 2025 Ahmet Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo import models


class Base(models.AbstractModel):
    _inherit = "base"

    def get_field_translations(self, field_name, langs=None):
        """
        Inherited to add "base_lang" to the translation data.
        """
        res = super().get_field_translations(field_name, langs=langs)
        if res and len(res) == 2:
            translations = res[0]
            lang_codes = [tr["lang"] for tr in translations]
            base_lang_by_code = {
                lang.code: lang.tr_base_lang_id.code
                for lang in self.env["res.lang"].search([("code", "in", lang_codes)])
                if lang.tr_base_lang_id
            }
            for tr in translations:
                tr["base_lang"] = base_lang_by_code.get(tr["lang"], False)
        return res
