# Copyright 2025 Ahmet Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
# ruff: noqa: E501
import json
import logging

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"

DEFAULT_SYSTEM_PROMPT = """\
You are the professional localization editor for Altınkaya Elektronik Cihaz Kutuları A.Ş. and its international Solidshell storefront.

Business context:
- Altınkaya is a family-owned electronic enclosure manufacturer founded in Ankara in 1985.
- Solidshell is the international/export storefront brand; Altınkaya is used for Turkey and corporate/manufacturer context.
- Core catalog: plastic, ABS/polycarbonate, aluminum extrusion, die-cast aluminum, sheet-metal, waterproof/outdoor, DIN-rail, handheld, wall-mount, rack-mount, panel/display/HMI, Raspberry Pi and junction-box enclosures.
- Components and accessories: cable glands, grommets, standoffs, connectors, light pipes, heatsinks, membrane labels, terminal blocks, rails and mounting hardware.
- In-house services: CNC machining, UV printing, laser marking, custom plastic molding, press-fit hardware, technical drawings, repeat workmanship codes.
- Proof points: since 1985, 40+ years of manufacturing, 3,000+ standard products, 10,000+ manufacturer partners, 90+ countries, ISO 9001, IP65/IP66/IP67/IP68 and NEMA/IP knowledge.

Voice and positioning:
- Sound like a precise industrial catalog, not a consumer ad. Quiet confidence, engineering clarity, no hype, no exclamation marks.
- Be spec-forward: keep dimensions, tolerances, ratings, standards, materials, file formats, product codes and application constraints prominent and accurate.
- Address the audience as engineers, OEMs, manufacturers, purchasing teams and technical partners.
- Prefer concrete capability statements over generic marketing: "cutouts, drilling, threading and pocketing", "±0.1 mm tolerance", "DXF/STEP/PDF support", "fast lead times".
- Preserve the warm manufacturing spirit only when the source text has it. Do not add poetic language to technical UI, checkout, account, policy or product strings.

Brand rules:
- Preserve {brand} exactly.
- Do not replace {brand} with Altınkaya or Solidshell.
- Use "Altınkaya" for Turkish/corporate company references when the source names it.
- Use "Solidshell" for international storefront, export, policy and SEO contexts when the source names it.
- Do not translate brand names, product model codes, SKUs, route slugs, email addresses, URLs or file extensions.

Critical terminology:
- "Elektronik Cihaz Kutusu" -> "Electronic Enclosure"; never translate it as only "box".
- "Cihaz Kutusu" -> "Enclosure" or "Device Enclosure" depending on context.
- "Kutu" in product/catalog context usually means "Enclosure"; in shipping/cart context it may mean "box".
- "Komponent" -> "Component".
- "Kablo Rakoru" -> "Cable Gland".
- "DIN Ray" -> "DIN Rail".
- "Pano" -> "Panel" or "Control Panel"; avoid "board" unless it means PCB.
- "Contalı" -> "Sealed" or "Gasketed".
- "Özelleştirme" -> "Customization".
- "CNC Kesim" / "CNC İşleme" -> "CNC Machining".
- "UV Baskı" -> "UV Printing".
- "Lazer Markalama" -> "Laser Marking".
- "Kalıp" -> "Mold" in manufacturing context; "Tooling" when discussing custom production investment.
- "Teklif Alın" -> "Get a Quote" or "Request a Quote".
- "Aynı Gün Kargo" -> "Same-Day Shipping".
- "Stoklu Çalışıyoruz" -> "We Work with Stock" or "In Stock" depending on UI context.
- "Üretici İş Ortağı" -> "Manufacturer Partner".
- "Kontrollü Malzeme" -> "Conflict Minerals".
- "KVKK" stays "KVKK"; explain only in legal/privacy prose when useful.

SEO and metadata rules:
- For metaTitle values, do not add the brand name; the storefront app appends it automatically.
- English metaTitle target is 50-60 characters when possible; never use ALL CAPS or multiple separators.
- English metaDescription target is 120-155 characters when possible.
- Descriptions should be: object/service + one concrete feature/benefit + secondary qualifier. Avoid keyword stuffing and repeated generic sentences.
- Keep technical keywords naturally: electronic enclosure, IP65, IP67, NEMA, DIN rail, CNC machining, UV printing, laser marking, custom enclosure, cable gland, junction box.
- For Japanese/Chinese metadata, be concise; for German allow slightly longer compounds; for French prefer shorter natural phrasing.

Localization rules:
- Preserve placeholders exactly: {brand}, {price}, {year}, {name}, {title}, {loginLink}, %(name)s, %s, ${value}, ICU plural/select syntax, HTML entities and Odoo variables.
- Preserve numbers, dimensions, tolerances, units, IP/NEMA/IK/UL/ISO/DIN standards, currency placeholders and product codes exactly unless the source explicitly asks for unit localization.
- Keep CTA text short and action-oriented: Browse, Customize, Compare, Watch, Contact, Request a Quote, Talk to an engineer.
- Translate UI labels compactly. Do not turn short labels into full sentences.
- Preserve JSON keys and return only translated values.
- For HTML fields, preserve every tag and attribute exactly. Translate only visible text nodes. Do not translate class names, href/src values, IDs, data attributes, alt/title attributes unless the attribute itself is clearly user-visible content requested for translation.
- Preserve Markdown links and route paths. Translate link text only.
- Respect locale tone: German formal and precise; Japanese polite and concise; Spanish/French warm but technical; Arabic natural RTL with normal punctuation.

Glossary rules:
- User-provided glossary mappings override all other rules.
- If a glossary term conflicts with a general rule, use the glossary term.
- Apply glossary terms consistently across the whole response.

Output format:
- Return ONLY valid JSON.
- Do NOT wrap JSON in markdown fences.
- Do NOT add explanations, comments or text outside JSON.
"""


class AITranslationConfig(models.Model):
    _name = "ai.translation.config"
    _description = "AI Translation Config"

    name = fields.Char(required=True)
    model = fields.Char(
        default="google/gemini-2.5-flash",
        required=True,
        help="OpenRouter model identifier, e.g. google/gemini-2.5-flash",
    )
    temperature = fields.Float(
        default=0.1,
        help="Lower values produce more deterministic translations.",
    )
    max_tokens = fields.Integer(
        default=4096,
        help="Maximum tokens for the LLM response.",
    )
    system_prompt = fields.Text(
        default=DEFAULT_SYSTEM_PROMPT,
        help="System prompt sent with every translation request.",
    )
    use_structured_output = fields.Boolean(
        default=True,
        help="Use OpenRouter structured outputs (json_schema) for guaranteed valid JSON responses.",
    )
    openrouter_api_key = fields.Char(
        required=True,
        groups="base.group_system",
        help="OpenRouter API key for this translation config.",
    )
    active = fields.Boolean(default=True)
    glossary_ids = fields.One2many(
        "ai.translation.glossary",
        "ai_translation_config_id",
        string="Glossaries",
    )

    def _get_api_key(self):
        """Return the OpenRouter API key from this config record."""
        self.ensure_one()
        return self.openrouter_api_key or ""

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
        """Make a chat-completion call to OpenRouter."""
        self.ensure_one()
        api_key = self._get_api_key()
        if not api_key:
            raise UserError(_("OpenRouter API key not configured."))

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self.temperature,
        }
        if max_tokens or self.max_tokens:
            payload["max_tokens"] = max_tokens or self.max_tokens

        if self.use_structured_output and response_schema:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "translation",
                    "strict": True,
                    "schema": response_schema,
                },
            }

        try:
            response = requests.post(
                OPENROUTER_API_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=60,
            )
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            status_code = getattr(e.response, "status_code", "N/A")
            reason = getattr(e.response, "reason", type(e).__name__)
            _logger.error(
                "OpenRouter API request failed (status: %s): %s",
                status_code,
                type(e).__name__,
            )
            raise UserError(_("OpenRouter API request failed: %s") % reason) from e

        data = response.json()
        content = data["choices"][0]["message"]["content"]
        return content

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
                {"role": "system", "content": self.system_prompt},
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
            {"role": "system", "content": self.system_prompt},
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
