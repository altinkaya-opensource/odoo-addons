# Copyright 2025 Ismail Çağan Yılmaz (https://github.com/milleniumkid)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    tax_office_name = fields.Char("Tax Office")

    def _search_due_days(self, operator, value):
        partners = self.search(
            [
                ("property_payment_term_id.line_ids.days", operator, value),
            ],
        )
        return [("id", "in", partners.ids)]

    z_muhasebe_kodu = fields.Char(
        "Zirve Muhasebe kodu", size=64, required=False, translate=False
    )
    z_receivable_export = fields.Char("Receivable Export", size=64, required=False)
    z_payable_export = fields.Char("Payable Export", size=64, required=False)
    purchase_default_account_id = fields.Many2one(
        "account.account",
        string="Purchase Default Account",
        required=False,
        help="Satın alma işlemlerinde varsayılan muhasebe hesabı.",
    )
    accounting_contact = fields.Many2one(
        "res.partner", string="Accounting Contact", required=False
    )
    devir_yapildi = fields.Boolean("Devir Yapıldı", default=False)
    due_days = fields.Integer(
        "Due Days",
        compute="_compute_due_days",
        store=False,
        default=0,
        search="_search_due_days",
    )

    def _compute_due_days(self):
        for record in self:
            if record.property_payment_term_id:
                record.due_days = max(
                    record.property_payment_term_id.line_ids.mapped("days") or [0],
                )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("ref") and self._needs_ref(vals=vals):
                vals["ref"] = self._get_next_ref(vals=vals)
                if vals.get("ref") and vals.get("country_id"):
                    country_id = self.env["res.country"].browse(vals["country_id"])
                    if country_id and country_id.code != "TR":
                        z_receivable_export = "120.Y%s" % (vals["ref"].strip() or "")
                        z_payable_export = "320.Y%s" % (vals["ref"].strip() or "")
                    else:
                        z_receivable_export = "120.%s" % (vals["ref"].strip() or "")
                        z_payable_export = "320.%s" % (vals["ref"].strip() or "")
                    vals.update(
                        {
                            "ref": vals["ref"],
                            "z_receivable_export": z_receivable_export,
                            "z_payable_export": z_payable_export,
                        }
                    )
        return super().create(vals_list)
