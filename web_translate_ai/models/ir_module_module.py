# Copyright 2026 Ahmet Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
import logging
import os

import polib

from odoo import _, models
from odoo.exceptions import ValidationError
from odoo.tools.misc import get_iso_codes

_logger = logging.getLogger(__name__)


class IrModuleModule(models.Model):
    _inherit = "ir.module.module"

    def action_open_ai_translate_module_wizard(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Translate Missing Terms"),
            "res_model": "ai.translate.module.wizard",
            "view_mode": "form",
            "view_id": self.env.ref(
                "web_translate_ai.view_ai_translate_module_wizard_form"
            ).id,
            "target": "new",
            "context": {
                "default_module_id": self.id,
            },
        }

    def _ai_translate_po_file(
        self, ai_config, i18n_path, filename, lang, regenerate=False
    ):
        lang_id = self.env["res.lang"].search([("code", "=", lang)], limit=1)
        po_path = os.path.join(i18n_path, filename)
        if regenerate or not os.path.isfile(po_path):
            self._save_translation_file(po_path, lang)

        try:
            po_file = polib.pofile(po_path)
        except (OSError, ValueError) as e:
            raise ValidationError(
                _(
                    "Could not parse translation file %(file)s. "
                    "Please fix the PO syntax or regenerate the translation file.\n"
                    "%(error)s"
                )
                % {
                    "file": po_path,
                    "error": e,
                }
            ) from e

        untranslated = [entry for entry in po_file if not entry.msgstr]
        if not untranslated:
            return True

        texts = [entry.msgid for entry in untranslated]
        _logger.info(
            "Translating %d missing terms in %s [%s] (%s -> %s)",
            len(texts),
            self.name,
            filename,
            "en_US",
            lang_id.code,
        )

        try:
            translations = ai_config._translate_texts_batch(
                source_lang="en_US",
                target_lang=lang_id.code,
                texts=texts,
                field_type="html",
            )
        except Exception as e:
            _logger.error(
                "Batch translation failed for module %s [%s]: %s",
                self.name,
                filename,
                e,
            )
            return False

        for entry, translated in zip(untranslated, translations, strict=True):
            entry.msgstr = translated

        po_file.save(po_path)
        return True

    def button_ai_translate_missing_terms(self, languages=None, regenerate=False):
        """Translate missing module PO terms with AI Translation."""
        self.ensure_one()
        ai_config = self.env.company.ai_translation_config_id
        if not ai_config:
            raise ValidationError(
                _("Please set AI Translation Config for the company first.")
            )

        i18n_path = self._get_i18n_path()
        langs = self._get_export_languages(languages=languages)
        failed_langs = []

        for lang in langs:
            if lang.code == "en_US":
                continue
            iso_code = get_iso_codes(lang.code)
            filename = f"{iso_code}.po"
            translated = self._ai_translate_po_file(
                ai_config,
                i18n_path,
                filename,
                lang.code,
                regenerate=regenerate,
            )
            if not translated:
                failed_langs.append(lang.code)

        if failed_langs:
            raise ValidationError(
                _("Translation failed for the following languages: %s")
                % ", ".join(failed_langs)
            )

        return True
