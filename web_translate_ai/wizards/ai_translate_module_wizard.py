# Copyright 2026 Ahmet Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo import _, fields, models
from odoo.exceptions import ValidationError


class AITranslateModuleWizard(models.TransientModel):
    _name = "ai.translate.module.wizard"
    _description = "AI Translate Module Wizard"

    module_id = fields.Many2one(
        "ir.module.module",
        required=True,
        readonly=True,
    )
    lang_ids = fields.Many2many(
        "res.lang",
        string="Languages",
        domain=[("active", "=", True), ("code", "!=", "en_US")],
        required=True,
    )
    regenerate_before_translate = fields.Boolean(
        string="Regenerate files before translating",
        default=True,
        help=(
            "Export the selected PO files again before AI translation. "
            "This makes newly added module terms available for translation."
        ),
    )

    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if "lang_ids" not in fields_list or res.get("lang_ids"):
            return res

        langs = self.env["res.lang"].search(
            [("active", "=", True), ("code", "!=", "en_US")]
        )
        res["lang_ids"] = [(6, 0, langs.ids)]
        return res

    def action_translate(self):
        self.ensure_one()
        if not self.lang_ids:
            raise ValidationError(_("Please select at least one language."))

        self.module_id.button_ai_translate_missing_terms(
            languages=self.lang_ids,
            regenerate=self.regenerate_before_translate,
        )
        return {"type": "ir.actions.act_window_close"}
