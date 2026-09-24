"""Move translation credentials and tuning to shared LLM records.

Read the legacy columns because their fields no longer exist in the registry,
preserving administrator settings over the shipped defaults.
"""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    cr.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = 'ai_translation_config'
        """
    )
    legacy_columns = {
        "model",
        "openrouter_api_key",
        "temperature",
        "max_tokens",
        "system_prompt",
    }
    if not legacy_columns.issubset({row[0] for row in cr.fetchall()}):
        _logger.info(
            "Skipping %s LLM migration: legacy columns are missing", "web_translate_ai"
        )
        return

    provider = env.ref("altinkaya_llm.provider_openrouter", raise_if_not_found=False)
    seeded_model = env.ref(
        "web_translate_ai.llm_model_translation", raise_if_not_found=False
    )
    if not provider or not seeded_model:
        _logger.warning(
            "Skipping %s LLM migration: provider or model record is missing",
            "web_translate_ai",
        )
        return

    cr.execute(
        """
        SELECT id, model, openrouter_api_key, temperature, max_tokens, system_prompt
        FROM ai_translation_config
        ORDER BY id
        """
    )
    rows = cr.dictfetchall()
    models = env["llm.model"].with_context(active_test=False)
    for index, row in enumerate(rows):
        api_key = row["openrouter_api_key"]
        if api_key and (not provider.api_key or provider.api_key == "CHANGE_ME"):
            provider.write({"api_key": api_key})

        config = env["ai.translation.config"].browse(row["id"])
        code = f"translation_{row['id']}"
        llm_model = (
            seeded_model
            if index == 0
            else models.search([("code", "=", code)], limit=1)
        )
        values = {
            "provider_id": provider.id,
            "model_slug": row["model"],
            "temperature": row["temperature"],
            "max_tokens": row["max_tokens"],
            "system_prompt": row["system_prompt"],
        }
        if llm_model:
            llm_model.write(values)
        else:
            values.update({"name": config.name, "code": code, "timeout": 60})
            llm_model = models.create(values)
        config.write({"llm_model_id": llm_model.id})

    _logger.info("Linked %s translation configs to LLM models", len(rows))
