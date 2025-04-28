# Copyright 2025 Ismail Çağan Yılmaz (https://github.com/milleniumkid)
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

import logging

from openai import OpenAI

from odoo import fields, models

_logger = logging.getLogger(__name__)


class IntelligenceProvider(models.Model):
    _name = "intelligence.provider"
    _description = "Intelligence Providers"

    name = fields.Char(string="Provider Name", required=True)
    provider_url = fields.Char(
        string="Provider URL", required=True, default="https://openrouter.ai/api/v1"
    )
    api_key = fields.Char(
        string="API Key",
        required=True,
        help="openai/gpt-3.5-turbo, openai/gpt-4, deepseek-chat...",
    )
    model_name = fields.Char(string="Model", required=True)
    prompt_ids = fields.One2many("intelligence.prompt", "provider_id", string="Prompts")
    system_role = fields.Selection(
        selection=[
            ("system", "System"),
            ("user", "User"),
            ("assistant", "Assistant"),
        ],
        string="System Role Prompt",
        default="system",
        help="Choose the role this prompt should use when talking to the LLM.\n"
        "- system: for instructions and context\n"
        "- user: for user input messages\n"
        "- assistant: for simulating assistant replies",
        required=True,
    )
    system_prompt = fields.Text(
        string="Default System Prompt",
        help="This content will be sent before every prompt.",
    )
    active = fields.Boolean(default=True)

    def action_test_connection(self):
        self.ensure_one()
        try:
            client = OpenAI(api_key=self.api_key, base_url=self.provider_url)
            response = client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": "Write 'Connection OK'"}],
                temperature=0.1,
            )
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": "Connection Test",
                    "message": f"Yanıt: {response.choices[0].message.content[:100]}...",
                    "type": "success",
                    "sticky": False,
                },
            }
        except Exception as e:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": "Connection Test Failed",
                    "message": str(e),
                    "type": "danger",
                    "sticky": True,
                },
            }

    def action_test_prompts(self):
        self.ensure_one()
        client = OpenAI(api_key=self.api_key, base_url=self.provider_url)
        results = []
        for prompt in self.prompt_ids:
            try:
                messages = [
                    {
                        "role": self.system_role,
                        "content": self.system_prompt or "System prompt empty",
                    },
                    {
                        "role": prompt.system_role or "user",
                        "content": prompt.prompt_text,
                    },
                ]
                response = client.chat.completions.create(
                    model=self.model_name,
                    messages=messages,
                    temperature=0.3,
                )
                output = response.choices[0].message.content.strip()
                results.append(f"**{prompt.name}**:\n{output[:200]}...")
            except Exception as e:
                results.append(f"**{prompt.name}**:\n{str(e)}")
        full_message = "\n\n".join(results)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Prompt Test",
                "message": full_message,
                "type": "warning",
                "sticky": True,
            },
        }
