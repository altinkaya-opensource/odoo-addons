"""Replace the shipped translation prompt with the current one.

The seeded record is noupdate, so the new prompt from the data file never
reaches existing databases. Only the exact previous shipped prompt is replaced,
matched by its SHA-256, so an administrator's own edits are kept.
"""

import hashlib
import logging
import xml.etree.ElementTree as ET

from odoo import SUPERUSER_ID, api
from odoo.modules import get_module_resource

_logger = logging.getLogger(__name__)

RECORD_XMLID = "web_translate_ai.llm_model_translation"
PREVIOUS_PROMPT_MARKER = "Do not replace {brand} with Altınkaya or "
PREVIOUS_PROMPT_SHA256 = (
    "36c0ef127a68ff44dcbab9a29e7cb5ed84d070a285025a57915d315c4afb22a5"
)


def _digest(prompt):
    """Return the SHA-256 of a prompt, ignoring surrounding whitespace."""
    return hashlib.sha256((prompt or "").strip().encode()).hexdigest()


def _shipped_system_prompt():
    """Return the system prompt shipped in the seeded data file."""
    data_file = get_module_resource("web_translate_ai", "data", "llm_model_data.xml")
    root = ET.parse(data_file).getroot()
    record = root.find(".//record[@id='llm_model_translation']")
    return record.find("field[@name='system_prompt']").text


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    llm_model = env.ref(RECORD_XMLID, raise_if_not_found=False)
    if not llm_model:
        return
    prompt = llm_model.system_prompt or ""
    if _digest(prompt) != PREVIOUS_PROMPT_SHA256:
        if PREVIOUS_PROMPT_MARKER in prompt:
            _logger.warning(
                "The translation prompt was edited, so it is kept. Apply the brand "
                "rule changes to it by hand."
            )
        return
    llm_model.write({"system_prompt": _shipped_system_prompt()})
    _logger.info("Replaced the previous shipped translation prompt")
