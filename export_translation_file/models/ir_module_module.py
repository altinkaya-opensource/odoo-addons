# Copyright 2024 Ahmet Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
import contextlib
import io
import logging
import os

import polib

from odoo import _, models, tools
from odoo.exceptions import ValidationError
from odoo.modules import get_module_path
from odoo.tools.misc import get_iso_codes

_logger = logging.getLogger(__name__)


class IrModuleModule(models.Model):
    _inherit = "ir.module.module"

    def button_save_translation(self):
        _format = "po"

        i18n_path = os.path.join(get_module_path(self.name), "i18n")
        if not os.path.isdir(i18n_path):
            os.mkdir(i18n_path)

        lang_obj = self.env["res.lang"]
        langs = lang_obj.search([("active", "=", True)])

        files = [(f"{self.name}.pot", False)]
        for lang in langs:
            iso_code = get_iso_codes(lang.code)
            filename = f"{iso_code}.{_format}"
            files.append((filename, lang.code))

        for filename, lang in files:
            path = os.path.join(i18n_path, filename)
            with contextlib.closing(io.BytesIO()) as buf:
                tools.trans_export(lang, [self.name], buf, _format, self._cr)
                with open(path, "w") as f:
                    f.write(buf.getvalue().decode("utf-8"))
        return True

    def _translate_po_file(self, deepl_account_id, i18n_path, filename, lang):
        lang_id = self.env["res.lang"].search([("code", "=", lang)], limit=1)
        po_path = os.path.join(i18n_path, filename)
        po_file = polib.pofile(po_path)
        for entry in po_file:
            if entry.msgstr:  # Skip if already translated
                continue

            try:
                translated_text = deepl_account_id._translate(
                    text=entry.msgid,
                    source_lang="en_US",
                    target_lang=lang_id.code,
                    field_type="html",
                )
                entry.msgstr = translated_text
            except Exception as e:
                _logger.error(
                    "Error while translating field '%s' in view %s [%s]: %s",
                    entry.msgid,
                    self.name,
                    self.id,
                    e,
                )
                continue
        po_file.save(po_path)

    def button_translate_missing_terms(self):
        """
        Translate views and code strings with single click. This method
        depends on DeepL Web Translate module.
        """
        self.ensure_one()
        deepl_module = self.search(
            [("state", "=", "installed"), ("name", "=", "web_translate_deepl")]
        )
        if not deepl_module:
            raise ValidationError(
                _(
                    "DeepL Translation module is not installed."
                    " Install it first to use this module."
                    " Technical name: web_translate_deepl"
                )
            )

        files = []
        deepl_account_id = self.env.company.deepl_account_id

        if not deepl_account_id:
            raise ValidationError(_("Please set DeepL Account for the company first."))

        i18n_path = os.path.join(get_module_path(self.name), "i18n")
        if not os.path.isdir(i18n_path):
            os.mkdir(i18n_path)

        lang_obj = self.env["res.lang"]
        langs = lang_obj.search([("active", "=", True)])

        for lang in langs:
            iso_code = get_iso_codes(lang.code)
            filename = f"{iso_code}.po"
            files.append((filename, lang.code))

        for filename, lang in files:
            self.with_delay(channel="root.0")._translate_po_file(
                deepl_account_id, i18n_path, filename, lang
            )
