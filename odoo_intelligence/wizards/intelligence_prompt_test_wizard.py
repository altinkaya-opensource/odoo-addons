# Copyright 2025 Ismail Çağan Yılmaz (https://github.com/milleniumkid)
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

import html

from openai import OpenAI

from odoo import api, fields, models
from odoo.exceptions import UserError


class IntelligencePromptTestWizard(models.TransientModel):
    _name = "intelligence.prompt.test.wizard"
    _description = "Prompt Test Wizard"

    prompt_id = fields.Many2one("intelligence.prompt", string="Prompt Name")
    model_id = fields.Many2one("ir.model", string="Model", required=True)
    record_id = fields.Many2oneReference(
        string="Record", model_field="model_id", required=True
    )
    user_id = fields.Many2one("res.users", string="User", required=True)
    lang = fields.Selection(
        selection=lambda self: self.env["res.lang"].get_installed(),
        string="Language",
        required=True,
    )
    body_html = fields.Html(string="Prompt", sanitize=False)

    @api.onchange("user_id")
    def _onchange_user_id(self):
        if self.user_id:
            self.lang = self.user_id.lang

    @api.onchange("model_id")
    def _onchange_model_id(self):
        self.record_id = False

    def _render_body_html(self):
        self.ensure_one()

        if not self.body_html:
            return ""

        clean_html = html.unescape(self.body_html or "").replace("&nbsp;", "&#160;")

        template_key = "intelligence.prompt.test.wizard.temp_template"
        temp_view = self.env["ir.ui.view"].create(
            {
                "name": "Temporary Translation Template",
                "type": "qweb",
                "key": template_key,
                "arch": f'<t t-name="{template_key}">{clean_html}</t>',
            }
        )

        try:
            rendered_html = self.env["ir.qweb"]._render(
                template_key,
                values={
                    "object": self.env[self.model_id.model].browse(self.record_id),
                    "user": self.user_id or self.env.user,
                },
            )
        finally:
            temp_view.unlink()

        return (
            rendered_html.decode("utf-8")
            if isinstance(rendered_html, bytes)
            else rendered_html
        )

    def action_test(self):
        self.ensure_one()
        provider = self.prompt_id.provider_id
        try:
            rendered_html = self._render_body_html()
            client = OpenAI(api_key=provider.api_key, base_url=provider.provider_url)
            messages = [
                {
                    "role": self.prompt_id.system_role or "system",
                    "content": f"{self.prompt_id.prompt_text}{self.lang}"
                    or f"Translate this HTML content to {self.lang}",
                },
                {"role": "user", "content": rendered_html},
            ]
            response = client.chat.completions.create(
                model=provider.model_name,
                messages=messages,
                temperature=self.prompt_id.temperature or 0.5,
            )
            output = response.choices[0].message.content

        except Exception as e:
            raise UserError(f"Translation test failed: {str(e)}")
        self.body_html = output
        return {
            "type": "ir.actions.act_window",
            "res_model": "intelligence.prompt.test.wizard",
            "view_mode": "form",
            "res_id": self.id,
            "target": "new",
        }
