# Copyright 2025 Ahmet Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class AITranslationGlossary(models.Model):
    _name = "ai.translation.glossary"
    _description = "AI Translation Glossary"

    name = fields.Char(compute="_compute_name", store=True)
    ai_translation_config_id = fields.Many2one(
        "ai.translation.config",
        string="AI Translation Config",
        required=True,
    )
    source_lang_id = fields.Many2one(
        "res.lang",
        string="Source Language",
        required=True,
    )
    target_lang_id = fields.Many2one(
        "res.lang",
        string="Target Language",
        required=True,
    )
    line_ids = fields.One2many(
        "ai.translation.glossary.line",
        "ai_translation_glossary_id",
        string="Entries",
    )

    _sql_constraints = [
        (
            "unique_lang_pair_per_config",
            "unique (ai_translation_config_id, source_lang_id, target_lang_id)",
            "A glossary for this language pair already exists in this config.",
        )
    ]

    @api.depends("source_lang_id", "target_lang_id")
    def _compute_name(self):
        for record in self:
            src = record.source_lang_id.name or "?"
            tgt = record.target_lang_id.name or "?"
            record.name = f"{src} → {tgt}"

    @api.constrains("source_lang_id", "target_lang_id")
    def _check_languages(self):
        for record in self:
            if record.source_lang_id == record.target_lang_id:
                raise ValidationError(
                    _("Source and target languages must be different.")
                )


class AITranslationGlossaryLine(models.Model):
    _name = "ai.translation.glossary.line"
    _description = "AI Translation Glossary Line"

    ai_translation_glossary_id = fields.Many2one(
        "ai.translation.glossary",
        string="Glossary",
        readonly=True,
    )
    source_term = fields.Char(required=True)
    target_term = fields.Char(required=True)

    _sql_constraints = [
        (
            "source_term_uniq",
            "unique (ai_translation_glossary_id, source_term)",
            "Source term must be unique in a glossary.",
        )
    ]
