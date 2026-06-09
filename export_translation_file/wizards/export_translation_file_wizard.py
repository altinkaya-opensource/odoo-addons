# Copyright 2026 Ahmet Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo import _, fields, models
from odoo.exceptions import ValidationError


class ExportTranslationFileWizard(models.TransientModel):
    _name = "export.translation.file.wizard"
    _description = "Export Translation File Wizard"

    module_id = fields.Many2one(
        "ir.module.module",
        required=True,
        readonly=True,
    )
    lang_ids = fields.Many2many(
        "res.lang",
        string="Languages",
        domain=[("active", "=", True)],
        required=True,
    )

    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if "lang_ids" not in fields_list or res.get("lang_ids"):
            return res

        langs = self.env["res.lang"].search([("active", "=", True)])
        res["lang_ids"] = [(6, 0, langs.ids)]
        return res

    def action_apply(self):
        self.ensure_one()
        if not self.lang_ids:
            raise ValidationError(_("Please select at least one language."))

        self.module_id.button_save_translation(languages=self.lang_ids)
        return {"type": "ir.actions.act_window_close"}
