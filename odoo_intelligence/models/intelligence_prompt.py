# Copyright 2025 Ismail Çağan Yılmaz (https://github.com/milleniumkid)
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

from odoo import models, fields

class IntelligencePrompt(models.Model):
    _name = 'intelligence.prompt'
    _description = 'Intelligence Prompts'

    name = fields.Char(string='Prompt Name', required=True)
    provider_id = fields.Many2one('intelligence.provider', string='LLM Provider', required=True, ondelete='cascade')
    model_id = fields.Many2one('ir.model', string='Target Model', required=True, ondelete='cascade')
    system_role = fields.Selection(related='provider_id.system_role', string="System Role (Provider)", readonly=True, store=True)
    prompt_text = fields.Char(string='System Prompt Text', required=True)
    body_html = fields.Html(string='HTML Template (QWeb)', sanitize=False)
    temperature = fields.Float(string='Temperature', default=0.5)
    active = fields.Boolean(default=True)
    
    def action_test_prompt(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'intelligence.prompt.test.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_prompt_id': self.id,
                'default_model_id': self.model_id.id,
                'default_body_html': self.body_html,
            }
        }
