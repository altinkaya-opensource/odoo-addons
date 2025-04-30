from collections import defaultdict

from odoo import api, fields, models
from odoo.tools.safe_eval import safe_eval


class XMakine(models.Model):
    _name = "x.makine"
    _description = "X Makine"
    _order = "name"

    x_group = fields.Char(
        "Bölüm",
        size=128,
    )
    x_kod = fields.Char("Makine Kodu", size=128)
    x_name = fields.Char("Makine Adı", size=128)
    name = fields.Char("Makine Numarası", size=128)


class MrpProduction(models.Model):
    _inherit = "mrp.production"
    mo_printed = fields.Boolean("Manufacting Order Printed", default=False)
    sale_id = fields.Many2one("sale.order", string="Sale Order")
    sale_note = fields.Text("Sale Note", related="sale_id.internal_note", readonly=True)
    active_rule_id = fields.Many2one("stock.rule", string="Active Rule")
    date_planned = fields.Datetime("Planned Date")
    date_start2 = fields.Datetime("Date Start")
    date_finished2 = fields.Datetime("Date End")
    process_id = fields.Many2one(
        "mrp.routing",
        string="Rota",
        readonly=True,
        related="bom_id.routing_id",
        store=True,
    )
    x_operator = fields.Many2one("hr.employee", "Uretimi Yapan Operator")
    x_note = fields.Text("Note")
    # TODO: @dogan workcenter_id alanini kullanabiliriz
    x_makine = fields.Many2one("x.makine", "Uretim Yapilan Makine")
    x_makine_kod = fields.Char(related="x_makine.x_kod", string="Makine", readonly=1)

    def _generate_moves(self):
        if self.env.context.get("context", {}).get("migration", False):
            return True
        for production in self:
            production._generate_finished_moves()
            factor = (
                production.product_uom_id._compute_quantity(
                    production.product_qty, production.bom_id.product_uom_id
                )
                / production.bom_id.product_qty
            )
            boms, lines = production.bom_id.explode(
                production.product_id,
                factor,
                picking_type=production.bom_id.picking_type_id,
            )
            production._generate_raw_moves(lines)
            # Check for all draft moves whether they are mto or not
            production._adjust_procure_method()
            production.move_raw_ids._action_confirm()
            production.move_raw_ids._action_assign()
        return True

    def get_product_route(self):
        def _get_next_moves(move_id):
            if move_id:
                next_moves = _get_next_moves(fields.first(move_id.move_dest_ids))
                if next_moves:
                    return move_id | next_moves
                else:
                    return move_id
            return False

        if self.move_dest_ids:
            route = []
            for m in _get_next_moves(fields.first(self.move_dest_ids)):
                if m.picking_id.id:
                    route.append(("picking", m.picking_id))
                elif m.raw_material_production_id.id:
                    route.append(("production", m.raw_material_production_id))

            res = route
        else:
            res = False

        return res

    def _get_product_pickings(self):
        def _get_next_moves(move_id):
            if move_id:
                next_moves = _get_next_moves(move_id.move_dest_id)
                if next_moves:
                    return move_id | next_moves
                else:
                    return move_id
            return False

        for mo in self:
            if mo.move_finished_ids:
                mo.id = _get_next_moves(mo.move_finished_ids[0]).mapped("picking_id")
            else:
                mo.id = False

    @api.onchange("process_id")
    def onchange_routing_id(self):
        if self.process_id.location_id:
            self.location_src_id = self.process_id.location_id
            self.location_dest_id = self.process_id.location_id

    @api.model_create_multi
    def create(self, vals_list):
        """
        Inherited to set the sale order to the production order if
        it is created from a sale order.
        """
        productions = super().create(vals_list)

        def _get_sale_line(moves):
            if moves and moves[0].sale_line_id:
                return moves[0].sale_line_id
            if moves and moves[0].move_dest_ids:
                return _get_sale_line(moves[0].move_dest_ids)
            return False

        for prod in productions:
            sale_line = _get_sale_line(
                prod.move_finished_ids and prod.move_finished_ids[0]
            )
            if sale_line:
                prod.write(
                    {
                        "sale_id": sale_line.order_id.id,
                    }
                )

        return productions

    def button_print_prod_order(self):
        return self.env.ref("mrp.action_report_production_order").report_action(self)

    def action_print_product_label(self):
        self.ensure_one()
        action = (
            self.env.ref("product_label_print.action_print_pack_barcode_wiz")
            .sudo()
            .read()[0]
        )

        # Ensure context is a dictionary
        action_context = action.get("context")
        if isinstance(action_context, str):
            try:
                action_context = safe_eval(action_context)  # Convert string to dict
            except Exception:
                action_context = {}  # Fallback to empty dict if conversion fails

        # Merge context properly
        action["context"] = {
            **action_context,
            "default_restrict_single": True,
            "active_ids": [self.product_id.id],
        }
        return action

    def action_set_production_started(self):
        for production in self:
            production.write(
                {"state": "progress", "date_start2": fields.Datetime.now()}
            )

    def _action_cancel(self):
        """
        Overriden prevent destination move and picking cancellation
        """
        documents_by_production = {}
        for production in self:
            documents = defaultdict(list)
            for move_raw_id in self.move_raw_ids.filtered(
                lambda m: m.state not in ("done", "cancel")
            ):
                iterate_key = self._get_document_iterate_key(move_raw_id)
                if iterate_key:
                    document = self.env["stock.picking"]._log_activity_get_documents(
                        {move_raw_id: (move_raw_id.product_uom_qty, 0)},
                        iterate_key,
                        "UP",
                    )
                    for key, value in document.items():
                        documents[key] += [value]
            if documents:
                documents_by_production[production] = documents
            # log an activity on Parent MO if child MO is cancelled.
            finish_moves = production.move_finished_ids.filtered(
                lambda x: x.state not in ("done", "cancel")
            )
            if finish_moves:
                production._log_downside_manufactured_quantity(
                    {
                        finish_move: (production.product_uom_qty, 0.0)
                        for finish_move in finish_moves
                    },
                    cancel=True,
                )

        self.workorder_ids.filtered(
            lambda x: x.state not in ["done", "cancel"]
        ).action_cancel()

        raw_moves = self.move_raw_ids.filtered(
            lambda x: x.state not in ("done", "cancel")
        )
        raw_moves._action_cancel()

        for production in self:
            production.state = "cancel"

    # TODO: this function changed to _update_raw_moves. Check the changes.
    # def _update_raw_move(self, bom_line, line_data):
    #     """Inherited to work with split procurements.
    #     If we found multiple moves that combined MTM and MTS,
    #     we need to change logic of this method.

    #     ADET ARTARSA:
    #     1) MTS miktarını maksimuma çıkar, MTO'yu arttır

    #     ADET AZALIRSA:
    #     1) Eğer MTS hepsini karşılıyorsa MTO'yu iptal et, MTS'yi güncelle.
    #     2) Eğer MTS hepsini karşılamıyorsa, MTS'yi sabit tut, MTO'yu güncelle.
    #     """
    #     new_qty = line_data["qty"]
    #     self.ensure_one()
    #     move = self.move_raw_ids.filtered(
    #         lambda x: x.bom_line_id.id == bom_line.id
    #         and x.state not in ("done", "cancel")
    #     )
    #     if len(move) == 2:
    #         mts_move = move.filtered(lambda x: x.procure_method == "make_to_stock")
    #         mto_move = move.filtered(lambda x: x.procure_method == "make_to_order")
    #         # Handle the case where there is no split procurement but we have 2 moves
    #         if not mts_move or not mto_move:
    #             return super(MrpProduction, self)._update_raw_move(bom_line, line_data) # noqa
    #         old_qty = sum(move.mapped("product_uom_qty"))
    #         if new_qty > old_qty:
    #             # Firstly, try to maximize MTS Move Qty
    #             mts_move.write(
    #                 {
    #                     "product_uom_qty": mts_move.reserved_availability
    #                     + mts_move.availability
    #                 }
    #             )
    #             mto_move.write({"product_uom_qty": new_qty - mts_move.product_uom_qty}) # noqa
    #         else:
    #             if mts_move.product_uom_qty >= new_qty:
    #                 # Update the MTS Move
    #                 mts_move.write({"product_uom_qty": new_qty})
    #                 mto_move.write(
    #                     {
    #                         "product_uom_qty": 0,
    #                         "quantity_done": 0,
    #                         # "raw_material_production_id": False,
    #                     }
    #                 )
    #                 # mto_move._action_cancel()
    #             else:
    #                 # Update the MTO Move
    #                 mto_move.write(
    #                     {"product_uom_qty": new_qty - mts_move.product_uom_qty}
    #                 )
    #                 # Update the MTS Move
    #                 mts_move.write(
    #                     {"product_uom_qty": new_qty - mto_move.product_uom_qty}
    #                 )
    #         move._recompute_state()
    #         move._action_assign()
    #         # There is no module that uses this method but Odoo's
    #         # MRP itself and it doesn't use return value of this method.
    #         # But we return it as the same anyway.
    #         return mts_move, old_qty, new_qty
    #     else:
    #         return super(MrpProduction, self)._update_raw_move(bom_line, line_data)

    def _rearrange_procurement_priorities(self):
        """
        Rearrange the priorities of the productions which are created from procurement
        rules.
        0: Not urgent
        1: Normal
        2: Urgent
        3: Very Urgent
        :return:
        """
        ongoing_productions = self.search(
            [
                ("state", "in", ("confirmed", "planned", "progress")),
                ("procurement_group_id.sale_id", "=", False),
            ]
        )
        for production in ongoing_productions:
            stock_rules = self.env["stock.warehouse.orderpoint"].search(
                [("product_id", "=", production.product_id.id)]
            )
            if stock_rules:
                total_minimum_qty = sum(stock_rules.mapped("product_min_qty"))
                total_available_qty = sum(stock_rules.mapped("product_location_qty"))
                # set urgent if available qty is less than 25% of minimum required qty
                if total_available_qty < (total_minimum_qty * 0.25):
                    production.priority = "2"
        return True
