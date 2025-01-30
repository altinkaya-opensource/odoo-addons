# Copyright 2023 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo import _, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_round


class MrpBoMWCParameter(models.Model):
    _name = "mrp.bom.wcparameter"
    _description = "Mrp Bom WCParameter"

    bom_id = fields.Many2one("mrp.bom", string="BoM")
    routing_wc_id = fields.Many2one("mrp.routing.workcenter", "Workcenter")
    cycle_nbr = fields.Float("Cycle Number")
    hour_nbr = fields.Float("Cycle Time(Hour)")
    time_start = fields.Float("Time Before Prod.")
    time_stop = fields.Float("Time After Prod.")

class MRPBoM(models.Model):
    _inherit = "mrp.bom"

    bom_template_line_ids = fields.One2many(
        "mrp.bom.template.line", "bom_id", "BoM Template Lines"
    )
    
    wc_parameter_ids = fields.One2many(
        "mrp.bom.wcparameter", "bom_id", "Workcenter Parameters"
    )
    
    categ_id = fields.Many2one(
        "product.category",
        related="product_tmpl_id.categ_id",
        string="Category",
        store=True,
        readonly=True,
    )
    
    checked = fields.Boolean(
        string="Kontrol Edildi", help="Bileşenler ve ağırlıkları kontrol edildi."
    )
    
    tool_product_id = fields.Many2one("product.product", string="Tool")

    def explode(self, product, quantity, picking_type=False):
        """
        This method is copied from mrp/models/mrp_bom.py
        and modified to use bom_template_line_ids within bom_line_ids
        """
        from collections import defaultdict

        graph = defaultdict(list)
        V = set()

        def check_cycle(v, visited, recStack, graph):
            visited[v] = True
            recStack[v] = True
            for neighbour in graph[v]:
                if not visited[neighbour]:
                    if check_cycle(neighbour, visited, recStack, graph):
                        return True
                elif recStack[neighbour]:
                    return True
            recStack[v] = False
            return False

        boms_done = [
            (
                self,
                {
                    "qty": quantity,
                    "product": product,
                    "original_qty": quantity,
                    "parent_line": False,
                },
            )
        ]
        lines_done = []
        V |= set([product.product_tmpl_id.id])

        bom_lines = [
            (bom_line, product, quantity, False, "bom_line")
            for bom_line in self.bom_line_ids
        ]
        # Add bom template lines
        bom_lines += [
            (bom_line, product, quantity, False, "tmpl_line")
            for bom_line in self.bom_template_line_ids
        ]
        for bom_line in self.bom_line_ids:
            V |= set([bom_line.product_id.product_tmpl_id.id])
            graph[product.product_tmpl_id.id].append(
                bom_line.product_id.product_tmpl_id.id
            )

        # Add bom template lines
        for bom_line in self.bom_template_line_ids:
            V |= set([bom_line.product_tmpl_id.id])
            graph[product.product_tmpl_id.id].append(bom_line.product_tmpl_id.id)
        while bom_lines:
            current_line, current_product, current_qty, parent_line, line_type = (
                bom_lines[0]
            )
            bom_lines = bom_lines[1:]

            if current_line._skip_bom_line(current_product):
                continue

            line_quantity = current_qty * current_line.product_qty
            if line_type == "bom_line":
                line_product = current_line.product_id
            else:
                line_product = current_line._match_possible_variant(current_product)
                if not line_product:
                    continue

            bom = self._bom_find(
                products=line_product,
                picking_type=picking_type or self.picking_type_id,
                company_id=self.company_id.id,
            )
            bom = bom[line_product]
            if bom.type == "phantom":
                converted_line_quantity = current_line.product_uom_id._compute_quantity(
                    line_quantity / bom.product_qty, bom.product_uom_id
                )
                bom_lines = [
                    (
                        line,
                        current_line.product_id,
                        converted_line_quantity,
                        current_line,
                    )
                    for line in bom.bom_line_ids
                ] + bom_lines
                for bom_line in bom.bom_line_ids:
                    graph[current_line.product_id.product_tmpl_id.id].append(
                        bom_line.product_id.product_tmpl_id.id
                    )
                    if bom_line.product_id.product_tmpl_id.id in V and check_cycle(
                        bom_line.product_id.product_tmpl_id.id,
                        {key: False for key in V},
                        {key: False for key in V},
                        graph,
                    ):
                        raise UserError(
                            _(
                                "Recursion error!  A product with a "
                                "Bill of Material should not have itself "
                                "in its BoM or child BoMs!"
                            )
                        )
                    V |= set([bom_line.product_id.product_tmpl_id.id])
                boms_done.append(
                    (
                        bom,
                        {
                            "qty": converted_line_quantity,
                            "product": current_product,
                            "original_qty": quantity,
                            "parent_line": current_line,
                        },
                    )
                )
            else:
                # We round up here because the user expects that if he has to
                # consume a little more, the whole UOM unit should be consumed.
                rounding = current_line.product_uom_id.rounding
                line_quantity = float_round(
                    line_quantity, precision_rounding=rounding, rounding_method="UP"
                )
                lines_done.append(
                    (
                        current_line,
                        {
                            "target_product": line_product,
                            "qty": line_quantity,
                            "product": current_product,
                            "original_qty": quantity,
                            "parent_line": parent_line,
                        },
                    )
                )

        return boms_done, lines_done
    
    
    # TODO: @dogan create work orders override
    #     @api.multi
    #     def _prepare_wc_line(self, wc_use, level=0, factor=1):
    #         res = super(MrpBoM, self)._prepare_wc_line(
    #             wc_use, level=level, factor=factor)
    #
    #         cycle_by_bom = self.env['mrp.config.settings']._get_parameter(
    #             'cycle.by.bom')
    #         if not (cycle_by_bom and cycle_by_bom.value == 'True'):
    #             production = self.env.context.get('production')
    #             factor = self._factor(production and production.product_qty or 1,
    #                                   self.product_efficiency,
    #                                   self.product_rounding)
    #
    #         wc_parameter_id = self.wc_parameter_ids.filtered(lambda wcp: wcp.routing_wc_id.id == wc_use.id)
    #
    #         if len(wc_parameter_id) == 1:
    #
    #             cycle = wc_parameter_id.cycle_nbr or 1.0
    #             hour = wc_parameter_id.hour_nbr * cycle
    #             time_start = wc_parameter_id.time_start
    #             time_stop = wc_parameter_id.time_stop
    #             res.update({
    #                 'cycle': cycle,
    #                 'hour': hour,
    #                 'time_start': time_start,
    #                 'time_stop': time_stop
    #             })
    #         return res

    # @api.multi
    # @api.onchange("routing_id")
    # def onchange_routing_id(self):
    #     res = super(MrpBoM, self).onchange_routing_id()

    #     self.wc_parameter_ids = False
    #     vals = []
    #     for wc_line in self.routing_id.operation_ids:
    #         vals.append(
    #             {
    #                 "routing_wc_id": wc_line.id,
    #             }
    #         )

    #     self.wc_parameter_ids = [(0, False, val) for val in vals]

    #     return res
