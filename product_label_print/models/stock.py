from odoo import models


class StockMove(models.Model):
    _inherit = "stock.move"

    def action_print_product_label(self):
        self.ensure_one()
        action = self.product_id.action_print_label()
        # Warehouse users can print labels without access to sales or MOs.
        picking = self.picking_id.sudo()
        if picking.picking_type_code != "outgoing" or not picking.sale_id:
            return action

        order = picking.sale_id
        mto_route = self.env.ref("stock.route_warehouse0_mto", raise_if_not_found=False)
        has_mto_line = mto_route and mto_route in order.order_line.route_id
        if not has_mto_line and not order.mrp_production_ids:
            return action

        lang = (
            picking.partner_id.lang
            or order.partner_id.commercial_partner_id.lang
            or "tr_TR"
        )
        action["context"]["default_lang"] = (
            lang if lang in ("en_US", "tr_TR") else "en_US"
        )
        return action
