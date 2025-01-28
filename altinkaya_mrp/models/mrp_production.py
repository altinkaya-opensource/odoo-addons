from odoo import models, fields, api, _
from odoo.exceptions import UserError


class XMakine(models.Model):
    # TODO: @dogan bence bu verilerin workcentera tasinmasi gerek uzerinde olmasi gerekli.
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
    # group_id = fields.Many2one('procurement.group',string='Producrement Group', related='move_prod_id.group_id')
    mo_printed = fields.Boolean("Manufacting Order Printed", default=False)
    sale_id = fields.Many2one("sale.order", string="Sale Order")
    sale_note = fields.Html("Sale Note", related="sale_id.note", readonly=True)
    active_rule_id = fields.Many2one("stock.rule", string="Active Rule")
    date_planned = fields.Datetime("Scheduled Date")
    date_start2 = fields.Datetime("Start Date")
    date_finished2 = fields.Datetime("End Date")
    priority = fields.Selection(
        [("0", "Not urgent"), ("1", "Normal"), ("2", "Urgent"), ("3", "Very Urgent")],
        string="Priority",
        default="0",
    )
    process_id = fields.Many2one(
        "mrp.routing.workcenter",
        string="Rota",
        readonly=True,
        compute="_compute_process_id",
        store=True,
    )

    @api.depends('bom_id')
    def _compute_process_id(self):
        for record in self:
            if record.bom_id and record.bom_id.operation_ids:
                record.process_id = record.bom_id.operation_ids[0].workcenter_id
            else:
                record.process_id = False
                
    x_operator = fields.Many2one("hr.employee", "Uretimi Yapan Operator")
    x_note = fields.Text("Not", size=256)
    # TODO: @dogan workcenter_id alanini kullanabiliriz
    x_makine = fields.Many2one("x.makine", "Uretim Yapilan Makine")
    x_makine_kod = fields.Char(related="x_makine.x_kod", string="Makine", readonly=1)
    procurement_group_name = fields.Char(
        compute="_get_procurement_group_name", string="Procurement Group", readonly=True
    )
    # product_pickings = fields.Many2many(compute="_get_product_pickings",string="Product Pickings", relation='stock.picking',
    #          readonly=True)

    # def _generate_moves(self):
    #     if self.env.context.get("context", {}).get("migration", False):
    #         return True
    #     for production in self:
    #         production._generate_finished_moves()
    #         factor = (
    #             production.product_uom_id._compute_quantity(
    #                 production.product_qty, production.bom_id.product_uom_id
    #             )
    #             / production.bom_id.product_qty
    #         )
    #         boms, lines = production.bom_id.explode(
    #             production.product_id,
    #             factor,
    #             picking_type=production.bom_id.picking_type_id,
    #         )
    #         production._generate_raw_moves(lines)
    #         # Check for all draft moves whether they are mto or not
    #         production._adjust_procure_method()
    #         production.move_raw_ids._action_confirm()
    #         production.move_raw_ids._action_assign()
    #     return True

    def _get_procurement_group_name(self):
        for mo in self:
            if mo.move_finished_ids:
                mo.id = mo.move_finished_ids[0].group_id.name
            else:
                mo.id = False

    # def get_product_route(self):
    #     def _get_next_moves(move_id):
    #         if move_id:
    #             next_moves = _get_next_moves(fields.first(move_id.move_dest_ids))
    #             if next_moves:
    #                 return move_id | next_moves
    #             else:
    #                 return move_id
    #         return False

    #     if self.move_dest_ids:
    #         route = []
    #         for m in _get_next_moves(fields.first(self.move_dest_ids)):
    #             if m.picking_id.id:
    #                 route.append(("picking", m.picking_id))
    #             elif m.raw_material_production_id.id:
    #                 route.append(("production", m.raw_material_production_id))

    #         res = route
    #     else:
    #         res = False

    #     return res

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
                next_moves = _get_next_moves(mo.move_finished_ids[0])
                mo.id = next_moves.mapped("picking_id") if next_moves else False
            else:
                mo.id = False

    # def name_search(self, name, args=None, operator="ilike", limit=80):
    #     if name:
    #         args += [("move_finished_ids[0].group_id.name", operator, name)]
    #     ids = self.search(args, limit=limit)
    #     return ids.name_get()

    # @api.onchange("routing_id")
    # def onchange_routing_id(self):
    #     if self.routing_id.location_id:
    #         self.location_src_id = self.routing_id.location_id
    #         self.location_dest_id = self.routing_id.location_id

    # @api.model
    # def create(self, values):
    #     production = super(MrpProduction, self).create(values)

    #     def _get_sale_line(moves):
    #         if moves and moves[0].sale_line_id:
    #             return moves[0].sale_line_id
    #         if moves and moves[0].move_dest_ids:
    #             return _get_sale_line(moves[0].move_dest_ids)
    #         return False

    #     sale_line = _get_sale_line(
    #         production.move_finished_ids and production.move_finished_ids[0]
    #     )
    #     if sale_line:
    #         production.write(
    #             {
    #                 "sale_id": sale_line.order_id.id or "",
    #             }
    #         )

    #     return production

    #     @api.model
    #     def _make_consume_line_from_data(self, production, product, uom_id, qty,
    #                                      uos_id, uos_qty):
    #         move_id = super(MrpProduction, self)._make_consume_line_from_data(
    #             production, product, uom_id, qty, uos_id, uos_qty)
    #         self.env['stock.move'].browse([move_id]).priority = production.priority
    #         return move_id

    #     @api.multi
    #     def action_confirm(self):
    #         res = super(MrpProduction, self).action_confirm()
    #         self.env.cr.commit()
    #         res2 = self.action_assign()
    #         return res

    def button_print_prod_order(self):
        return self.env.ref("mrp.action_report_production_order").report_action(self)

    # def action_print_product_label(self):
    #     self.ensure_one()
    #     aw_obj = self.env["ir.actions.act_window"].with_context(
    #         {"default_restrict_single": True}
    #     )
    #     action = aw_obj.for_xml_id(
    #         "product_label_print", "action_print_pack_barcode_wiz"
    #     )
    #     action.update(
    #         {
    #             "context": {
    #                 "default_restrict_single": True,
    #                 "active_ids": [self.product_id.id],
    #             }
    #         }
    #     )
    #     return action

    def action_create_procurement(self):
        return {}


    def action_make_mts(self):
        return {}

    # def action_set_production_started(self):
    #     for production in self:
    #         production.write({"state": "planned", "date_start2": fields.Datetime.now()})

    def _update_raw_move(self, bom_line, line_data):
        """Inherited to work with split procurements.
        If we found multiple moves that combined MTM and MTS,
        we need to change logic of this method.

        ADET ARTARSA:
        1) MTS miktarını maksimuma çıkar, MTO'yu arttır

        ADET AZALIRSA:
        1) Eğer MTS hepsini karşılıyorsa MTO'yu iptal et, MTS'yi güncelle.
        2) Eğer MTS hepsini karşılamıyorsa, MTS'yi sabit tut, MTO'yu güncelle.
        """
        new_qty = line_data["qty"]
        self.ensure_one()
        move = self.move_raw_ids.filtered(
            lambda x: x.bom_line_id.id == bom_line.id
            and x.state not in ("done", "cancel")
        )
        if len(move) == 2:
            mts_move = move.filtered(lambda x: x.procure_method == "make_to_stock")
            mto_move = move.filtered(lambda x: x.procure_method == "make_to_order")
            # Handle the case where there is no split procurement but we have 2 moves
            if not mts_move or not mto_move:
                return super(MrpProduction, self)._update_raw_moves(bom_line, line_data)
            old_qty = sum(move.mapped("product_uom_qty"))
            if new_qty > old_qty:
                # Firstly, try to maximize MTS Move Qty
                mts_move.write(
                    {
                        "product_uom_qty": mts_move.reserved_availability
                        + mts_move.availability
                    }
                )
                mto_move.write({"product_uom_qty": new_qty - mts_move.product_uom_qty})
            else:
                if mts_move.product_uom_qty >= new_qty:
                    # Update the MTS Move
                    mts_move.write({"product_uom_qty": new_qty})
                    mto_move.write(
                        {
                            "product_uom_qty": 0,
                            "quantity_done": 0,
                            # "raw_material_production_id": False,
                        }
                    )
                    # mto_move._action_cancel()
                else:
                    # Update the MTO Move
                    mto_move.write(
                        {"product_uom_qty": new_qty - mts_move.product_uom_qty}
                    )
                    # Update the MTS Move
                    mts_move.write(
                        {"product_uom_qty": new_qty - mto_move.product_uom_qty}
                    )
            move._recompute_state()
            move._action_assign()
            # There is no module that uses this method but Odoo's
            # MRP itself and it doesn't use return value of this method.
            # But we return it as the same anyway.
            return mts_move, old_qty, new_qty
        else:
            return super(MrpProduction, self)._update_raw_moves(bom_line, line_data)

    # @api.multi
    # def _rearrange_procurement_priorities(self):
    #     """
    #     Rearrange the priorities of the productions which are created from procurement
    #     rules.
    #     0: Not urgent
    #     1: Normal
    #     2: Urgent
    #     3: Very Urgent
    #     :return:
    #     """
    #     ongoing_productions = self.search(
    #         [
    #             ("state", "in", ("confirmed", "planned", "progress")),
    #             ("procurement_group_id.sale_id", "=", False),
    #         ]
    #     )
    #     for production in ongoing_productions:
    #         stock_rules = self.env["stock.warehouse.orderpoint"].search(
    #             [("product_id", "=", production.product_id.id)]
    #         )
    #         if stock_rules:
    #             total_minimum_qty = sum(stock_rules.mapped("product_min_qty"))
    #             total_available_qty = sum(stock_rules.mapped("product_location_qty"))
    #             # set urgent if available qty is less than 25% of minimum required qty
    #             if total_available_qty < (total_minimum_qty * 0.25):
    #                 production.priority = "2"
    #     return True
