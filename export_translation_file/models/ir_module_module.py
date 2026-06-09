# Copyright 2024 Ahmet Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
import contextlib
import io
import os

from odoo import _, models, tools
from odoo.modules import get_module_path
from odoo.tools.misc import get_iso_codes


class IrModuleModule(models.Model):
    _inherit = "ir.module.module"

    def _get_export_wizard_action(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Export Translation Files"),
            "res_model": "export.translation.file.wizard",
            "view_mode": "form",
            "view_id": self.env.ref(
                "export_translation_file.view_export_translation_file_wizard_form"
            ).id,
            "target": "new",
            "context": {
                "default_module_id": self.id,
            },
        }

    def _get_i18n_path(self):
        self.ensure_one()
        i18n_path = os.path.join(get_module_path(self.name), "i18n")
        os.makedirs(i18n_path, exist_ok=True)
        return i18n_path

    def _get_export_languages(self, languages=None):
        if languages is not None:
            return languages
        return self.env["res.lang"].search([("active", "=", True)])

    def _save_translation_file(self, path, lang, file_format="po"):
        with contextlib.closing(io.BytesIO()) as buf:
            tools.trans_export(lang, [self.name], buf, file_format, self._cr)
            with open(path, "w", encoding="utf-8") as f:
                f.write(buf.getvalue().decode("utf-8"))

    def action_open_save_translation_wizard(self):
        return self._get_export_wizard_action()

    def button_save_translation(self, languages=None):
        _format = "po"

        i18n_path = self._get_i18n_path()
        langs = self._get_export_languages(languages=languages)

        files = [(f"{self.name}.pot", False)]
        for lang in langs:
            iso_code = get_iso_codes(lang.code)
            filename = f"{iso_code}.{_format}"
            files.append((filename, lang.code))

        for filename, lang in files:
            path = os.path.join(i18n_path, filename)
            self._save_translation_file(path, lang, _format)
        return True
