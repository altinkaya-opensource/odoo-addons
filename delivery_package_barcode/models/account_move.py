# Copyright (C) 2025 Ahmet Yiğit Budak (https://github.com/yibudak)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
from odoo import api, fields, models


class AccountMove(models.Model):
    _inherit = "account.move"

    # Inhertied to add picking_ids in depends.
    @api.depends(
        "invoice_line_ids",
        "invoice_line_ids.move_line_ids",
        "invoice_line_ids.move_line_ids.picking_id",
    )
    def _compute_picking_ids(self):
        for invoice in self:
            invoice.picking_ids = invoice.mapped(
                "invoice_line_ids.move_line_ids.picking_id"
            )

    def action_post(self):
        """
        Inherited to set invoice_state automatically when invoice is correctly posted
        and has delivery_ref_no.

        This function supposed to be called on manual actions.
        """
        res = super().action_post()
        for inv in self.filtered(lambda move: move.is_invoice(include_receipts=True)):
            done_pickings = inv.picking_ids.filtered(
                lambda p: p.picking_type_code == "outgoing" and p.state == "done"
            )
            if inv.state == "posted" and done_pickings and inv.delivery_ref_no:
                done_pickings.write(
                    {
                        "invoice_state": "invoiced",
                    }
                )
        return res

    @api.model_create_multi
    def create(self, vals_list):
        res = super().create(vals_list)
        for inv in res.filtered(lambda move: move.is_invoice(include_receipts=True)):
            done_pickings = inv.picking_ids.filtered(
                lambda p: p.picking_type_code == "outgoing" and p.state == "done"
            )
            if (
                inv.partner_id.recalculate_shipping_cost
                and not any(inv.picking_ids.mapped("block_autoinvoicing"))
                and done_pickings
            ):
                inv._recompute_shipping_cost(done_pickings)
        return res

    def _recompute_shipping_cost(self, done_pickings):
        """Recompute shipping cost based on related pickings."""
        self.ensure_one()
        carrier_id = self.carrier_id
        total_shipping_weight = sum(done_pickings.mapped("picking_total_weight"))
        any_sale_id = fields.first(done_pickings.mapped("sale_id"))
        shipping_cost = carrier_id._get_price_available_price_section(
            any_sale_id, 1.0, 1.0, total_shipping_weight
        )
        price_currency = carrier_id._compute_currency(
            any_sale_id, shipping_cost, "company_to_pricelist"
        )
        if shipping_cost:
            old_carrier_lines = self.invoice_line_ids.filtered(
                lambda il: il.product_id == carrier_id.product_id
            )

            related_move_ids = old_carrier_lines.mapped("move_line_ids")

            # Remove existing shipping lines
            old_carrier_lines.unlink()

            account_id = (
                carrier_id.product_id.property_account_income_id.id
                or carrier_id.product_id.categ_id.property_account_income_categ_id.id
            )
            delivery_line = self.env["account.move.line"].create(
                {
                    "move_id": self.id,
                    "product_id": carrier_id.product_id.id,
                    "quantity": 1,
                    "price_unit": price_currency,
                    "name": carrier_id.product_id.display_name,
                    "account_id": account_id,
                    "tax_ids": [(6, 0, carrier_id.product_id.taxes_id.ids)],
                    "move_line_ids": [(6, 0, related_move_ids.ids)],
                }
            )

            # Apply the pricelist rules on the delivery line
            delivery_line.with_context(
                fixed_delivery_price=price_currency
            )._compute_price_unit()

        return True
