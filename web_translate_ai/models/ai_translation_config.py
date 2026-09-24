# Copyright 2025 Ahmet Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
# ruff: noqa: E501
import json
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AITranslationConfig(models.Model):
    _name = "ai.translation.config"
    _description = "AI Translation Config"

    name = fields.Char(required=True)
    # Keep nullable: SET NOT NULL fails on existing rows before migration backfills
    # this field, silently leaving the constraint absent. The form requires it.
    llm_model_id = fields.Many2one(
        "llm.model",
        string="LLM Model",
        help="Provider, model slug, prompt and tuning for this translation config.",
    )
    use_structured_output = fields.Boolean(
        default=True,
        help="Use OpenRouter structured outputs (json_schema) for guaranteed valid JSON responses.",
    )
    active = fields.Boolean(default=True)
    glossary_ids = fields.One2many(
        "ai.translation.glossary",
        "ai_translation_config_id",
        string="Glossaries",
    )

    def _build_glossary_text(self, source_lang, target_lang):
        """Build glossary text for a source→target language pair."""
        self.ensure_one()
        glossary = fields.first(
            self.glossary_ids.filtered(
                lambda g: (
                    g.source_lang_id.code == source_lang
                    and g.target_lang_id.code == target_lang
                )
            )
        )
        if not glossary:
            return ""
        lines = [
            f"{line.source_term.strip()} → {line.target_term.strip()}"
            for line in glossary.line_ids
        ]
        return "\n".join(lines)

    def _call_openrouter(
        self, messages, temperature=None, max_tokens=None, response_schema=None
    ):
        """Delegate chat completion to the linked LLM model."""
        self.ensure_one()
        if not self.llm_model_id:
            raise UserError(
                _("No LLM model is set on translation config '%s'.") % self.name
            )
        return self.llm_model_id._chat(
            messages,
            response_schema=response_schema if self.use_structured_output else None,
            schema_name="translation",
            temperature=temperature,
            max_tokens=max_tokens,
        )

    def _parse_json_response(self, content):
        """Strip markdown fences and parse JSON."""
        content = content.strip()
        if content.startswith("```json"):
            content = content[7:]
        elif content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()
        try:
            return json.loads(content)
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            _logger.warning("Failed to parse LLM JSON response: %s", content[:500])
            raise UserError(
                _(
                    "The AI returned an invalid JSON response. "
                    "Please try again or check the model settings.\n%s"
                )
                % content[:500]
            ) from e

    def _translate_batch(self, source_lang, translations_data):
        """
        Translate multiple target languages in a single LLM call.

        :param source_lang: Odoo language code of the source text (e.g. 'tr_TR').
        :param translations_data: list of dicts:
            [
                {
                    "target_lang": "de_DE",
                    "source_text": "...",
                    "field_type": "text" | "html",
                },
                ...
            ]
        :return: dict mapping target_lang -> translated text.
        """
        self.ensure_one()
        if not translations_data:
            return {}

        # Group by (source_text, field_type) to minimize prompts
        grouped = {}
        for item in translations_data:
            key = (item["source_text"], item["field_type"])
            grouped.setdefault(key, set()).add(item["target_lang"])

        result = {}
        for (source_text, field_type), target_lang_set in grouped.items():
            target_langs = sorted(target_lang_set)
            glossary_blocks = []
            for tl in target_langs:
                gtext = self._build_glossary_text(source_lang, tl)
                if gtext:
                    glossary_blocks.append(
                        f"Glossary for {source_lang} → {tl}:\n{gtext}"
                    )

            user_prompt = self._build_translation_prompt(
                source_lang=source_lang,
                source_text=source_text,
                target_langs=target_langs,
                field_type=field_type,
                glossary_text="\n\n".join(glossary_blocks),
            )

            messages = [
                {"role": "system", "content": self.llm_model_id.system_prompt},
                {"role": "user", "content": user_prompt},
            ]

            response_schema = None
            if self.use_structured_output:
                response_schema = self._build_response_schema(target_langs)

            content = self._call_openrouter(messages, response_schema=response_schema)
            parsed = self._parse_json_response(content)

            for tl in target_langs:
                if tl in parsed:
                    result[tl] = parsed[tl]
                else:
                    # Fallback: try language code without region
                    tl_short = tl.split("_")[0]
                    if tl_short in parsed:
                        result[tl] = parsed[tl_short]
                    else:
                        _logger.warning(
                            "Translation for %s missing in LLM response", tl
                        )
                        result[tl] = source_text

        return result

    def _build_response_schema(self, target_langs):
        """Build a JSON Schema for OpenRouter structured outputs."""
        properties = {}
        for tl in target_langs:
            properties[tl] = {
                "type": "string",
                "description": f"Translated text in {tl}",
            }
        return {
            "type": "object",
            "properties": properties,
            "required": target_langs,
            "additionalProperties": False,
        }

    def _build_translation_prompt(
        self, source_lang, source_text, target_langs, field_type, glossary_text=""
    ):
        """Build the user prompt for a translation request."""
        lang_list = ", ".join(target_langs)
        html_note = ""
        if field_type == "html":
            html_note = (
                "\nThis is an HTML field. You must preserve ALL HTML tags "
                "(<p>, <strong>, <br>, etc.) exactly as they appear. "
                "Only translate the visible text content.\n"
            )

        glossary_note = ""
        if glossary_text:
            glossary_note = f"\nUse the following glossary mappings:\n{glossary_text}\n"

        if self.use_structured_output:
            prompt = f"""Translate the following text into the requested languages.

Source language: {source_lang}
Text to translate: {source_text}{html_note}{glossary_note}
Target languages: {lang_list}
"""
        else:
            prompt = f"""Translate the following text into the requested languages.

Source language: {source_lang}
Text to translate: {source_text}{html_note}{glossary_note}
Target languages: {lang_list}

Return ONLY a valid JSON object where each key is the target language code and each value is the translated text. Do not wrap the JSON in markdown code fences. Do not add any text outside the JSON.

Expected format:
{{
    "{target_langs[0]}": "...",
    ...
}}
"""
        return prompt

    def _translate_single(self, source_lang, target_lang, text, field_type=None):
        """Translate a single text to one target language."""
        self.ensure_one()
        result = self._translate_batch(
            source_lang,
            [
                {
                    "target_lang": target_lang,
                    "source_text": text,
                    "field_type": field_type or "text",
                }
            ],
        )
        return result.get(target_lang, text)

    @api.model
    def rpc_translate(self, target_lang, text, field_type):
        """
        Public RPC method for single-language translation (called from frontend).
        """
        company_sudo = self.env.user.company_id.sudo()
        if not company_sudo.ai_translation_config_id:
            raise UserError(_("AI Translation config not found for this company!"))

        target_lang_id = self.env["res.lang"].search([("code", "=", target_lang)])
        base_lang_id = target_lang_id.tr_base_lang_id
        if not base_lang_id:
            raise UserError(
                _("Base language not found! Set translation base language for %s")
                % target_lang_id.display_name
            )

        return company_sudo.ai_translation_config_id._translate_single(
            base_lang_id.code,
            target_lang,
            text,
            field_type=field_type,
        )

    @api.model
    def rpc_translate_all(self, translations_data):
        """
        Public RPC method for batch translation (called from frontend).

        :param translations_data: list of dicts with keys:
            target_lang, source_text, field_type
        :return: dict mapping target_lang -> translated text
        """
        company_sudo = self.env.user.company_id.sudo()
        if not company_sudo.ai_translation_config_id:
            raise UserError(_("AI Translation config not found for this company!"))

        config = company_sudo.ai_translation_config_id
        lang_model = self.env["res.lang"]

        # Resolve base languages for each target and group by source_lang
        grouped_by_source = {}
        for item in translations_data:
            target_lang = item["target_lang"]
            target_lang_id = lang_model.search([("code", "=", target_lang)])
            base_lang_id = target_lang_id.tr_base_lang_id
            if not base_lang_id:
                continue
            grouped_by_source.setdefault(base_lang_id.code, []).append(
                {
                    "target_lang": target_lang,
                    "source_text": item["source_text"],
                    "field_type": item.get("field_type", "text"),
                }
            )

        if not grouped_by_source:
            return {}

        result = {}
        for source_lang, items in grouped_by_source.items():
            batch_result = config._translate_batch(source_lang, items)
            result.update(batch_result)

        return result

    @api.model
    def rpc_get_current_company_lang(self):
        """
        Return current company AI translation status and user language.
        Used by the frontend to decide whether to show AI buttons.
        """
        user_company = self.env.user.company_id
        return {
            "company_id": user_company.id,
            "ai_enabled": bool(user_company.ai_translation_config_id),
            "user_lang": self.env.user.lang,
        }

    def _translate_texts_batch(
        self, source_lang, target_lang, texts, field_type="text", chunk_size=30
    ):
        """
        Translate multiple different texts to the same target language in batches.

        :param source_lang: Source language code (e.g. 'en_US').
        :param target_lang: Target language code (e.g. 'tr_TR').
        :param texts: List of strings to translate.
        :param field_type: 'text' or 'html'.
        :param chunk_size: Number of texts per API call (default 30).
        :return: List of translated strings in the same order as input.
        """
        self.ensure_one()
        if not texts:
            return []

        results = []
        for i in range(0, len(texts), chunk_size):
            chunk = texts[i : i + chunk_size]
            chunk_result = self._translate_texts_chunk(
                source_lang, target_lang, chunk, field_type
            )
            results.extend(chunk_result)

        return results

    def _translate_texts_chunk(
        self, source_lang, target_lang, texts, field_type="text"
    ):
        """Translate a single chunk of texts."""
        self.ensure_one()
        if not texts:
            return []

        glossary_text = self._build_glossary_text(source_lang, target_lang)
        glossary_note = (
            f"\nUse the following glossary mappings:\n{glossary_text}\n"
            if glossary_text
            else ""
        )

        html_note = ""
        if field_type == "html":
            html_note = (
                "\nThese are HTML strings. Preserve ALL HTML tags exactly. "
                "Only translate visible text content.\n"
            )

        numbered = "\n".join(f'{idx}: "{text}"' for idx, text in enumerate(texts))

        user_prompt = f"""Translate the following texts from {source_lang} to {target_lang}.{html_note}{glossary_note}

Texts to translate:
{numbered}

Return ONLY a valid JSON object where each key is the number and each value is the translated text. Do not add any text outside the JSON.

Expected format:
{{
    "0": "...",
    "1": "...",
    ...
}}
"""

        messages = [
            {"role": "system", "content": self.llm_model_id.system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        response_schema = None
        if self.use_structured_output:
            properties = {}
            for idx in range(len(texts)):
                properties[str(idx)] = {
                    "type": "string",
                    "description": f"Translated text for item {idx}",
                }
            response_schema = {
                "type": "object",
                "properties": properties,
                "required": list(properties.keys()),
                "additionalProperties": False,
            }

        content = self._call_openrouter(messages, response_schema=response_schema)
        parsed = self._parse_json_response(content)

        return [parsed.get(str(idx), texts[idx]) for idx in range(len(texts))]

    def action_test_connection(self):
        """Quick connection test: translate 'Hello World' EN -> TR."""
        self.ensure_one()
        result = self._translate_single(
            "en_US", "tr_TR", "Hello World!", field_type="text"
        )
        raise UserError(
            _('OpenRouter API Success: "Hello World" translation: %s') % result
        )
