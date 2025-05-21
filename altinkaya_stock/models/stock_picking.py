##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (c) 2012-Present (<http://www.acespritech.com/>)
#    Acespritech Solutions Pvt.Ltd
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################
from odoo import api, fields, models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def open_sales_order(self):
        self.ensure_one()
        action = self.env.ref("sale.action_orders").sudo().read()[0]
        form = self.env.ref("sale.view_order_form")
        action["views"] = [(form.id, "form")]
        action["res_id"] = self.sale_id.id
        return action

    x_durum = fields.Selection(
        [
            ("1", "İthal Eksik"),
            ("2", "CNC Kesimde"),
            ("3", "Enjeksiyonda"),
            ("4", "Montajda"),
            ("5", "Çıkacak"),
            ("6", "ACİL"),
            ("7", "Müsteriyi Bekliyor"),
            ("8", "Profil Kesimde"),
            ("9", "Sac Üretiminde"),
            ("A", "Boyada"),
            ("B", "Piyasadan Teminde"),
        ],
        "Durumu",
        index=True,
    )
    hazirlayan = fields.Many2one("hr.employee", "Sevki Hazırlayan")
    country_id = fields.Many2one(
        "res.country",
        string="Country",
        related="partner_id.country_id",
        store=True,
    )
    partner_invoice_id = fields.Many2one(
        "res.partner",
        string="Invoice Address",
        related="sale_id.partner_invoice_id",
        store=True,
    )
    sales_uid = fields.Many2one(
        "res.users",
        string="Sales Person",
        related="sale_id.create_uid",
        store=True,
    )
    sale_note = fields.Text("Sale Note", related="sale_id.internal_note", readonly=True)
    trimmed_sale_note = fields.Text(
        compute="_compute_trimmed_sale_note",
        readonly=True,
    )

    package_ids = fields.Many2many(readonly=False)

    def action_see_packages(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("stock.action_package_view")
        move_line_packages = self.move_line_ids.mapped("result_package_id")
        direct_packages = self.package_ids
        packages = (move_line_packages | direct_packages).filtered(lambda p: p)
        action["domain"] = [("id", "in", packages.ids)]
        action["context"] = {"default_picking_id": self.id}
        return action

    @api.onchange("carrier_id")
    def _onchange_carrier_id(self):
        source = self.sale_id or self.purchase_id
        if self.carrier_id and source:
            source.write({"carrier_id": self.carrier_id.id})

    # def action_put_in_pack(self):
    #     self.ensure_one()
    #     return {
    #         "name": "Put in Pack",
    #         "type": "ir.actions.act_window",
    #         "res_model": "choose.delivery.package",
    #         "view_mode": "form",
    #         "target": "new",
    #         "context": {
    #             "default_picking_id": self.id,
    #         },
    #     }

    # def force_assign(self):
    #     for pick in self:
    #         move_ids = [
    #             x for x in pick.move_lines if x.state in ["confirmed", "waiting"]
    #         ]
    #         self.env["stock.move"].force_assign(moves=move_ids)
    #         pick.button_validate()
    #     return True

    def _compute_trimmed_sale_note(self):
        """
        Trims the sale note to the first 50 characters.
        """
        for picking in self:
            if picking.sale_note:
                picking.trimmed_sale_note = self.env[
                    "ir.fields.converter"
                ].text_from_html(picking.sale_note, max_chars=50)
            else:
                picking.trimmed_sale_note = ""
