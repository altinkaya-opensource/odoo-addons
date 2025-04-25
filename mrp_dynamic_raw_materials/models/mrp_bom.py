#
# Created on Mar 5, 2018
#
# @author: dogan
#

from odoo import _, fields, models
from odoo.exceptions import Warning as UserError


class MrpBoM(models.Model):
    _inherit = "mrp.bom"

    # Overridden original method and checked factor_attribute_id field
    def _check_cycle_in_graph(self, vertex, visited, recStack, graph):
        visited[vertex] = True
        recStack[vertex] = True
        for neighbour in graph[vertex]:
            if not visited[neighbour]:
                if self._check_cycle_in_graph(neighbour, visited, recStack, graph):
                    return True
            elif recStack[neighbour]:
                return True
        recStack[vertex] = False
        return False

    def _compute_line_quantity(self, line, product, current_qty):
        qty_extra = 0.0
        if line.factor_attribute_id:
            attribute_value_ids = product.attribute_value_ids
            attribute_value_id = attribute_value_ids.filtered(
                lambda v, line=line: v.attribute_id.id == line.factor_attribute_id.id
            )
            if attribute_value_id:
                qty_extra = attribute_value_id.numeric_value * line.attribute_factor
        return current_qty * (line.product_qty + qty_extra)

    def _process_phantom_bom(
        self, bom, line, line_quantity, current_product, quantity, graph, V
    ):
        converted_line_quantity = line.product_uom_id._compute_quantity(
            line_quantity / bom.product_qty, bom.product_uom_id
        )
        new_bom_lines = [
            (lam, line.product_id, converted_line_quantity, line, "bom_line")
            for lam in bom.bom_line_ids
        ]

        for bom_line in bom.bom_line_ids:
            graph[line.product_id.product_tmpl_id.id].append(
                bom_line.product_id.product_tmpl_id.id
            )
            if (
                bom_line.product_id.product_tmpl_id.id in V
                and self._check_cycle_in_graph(
                    bom_line.product_id.product_tmpl_id.id,
                    {key: False for key in V},
                    {key: False for key in V},
                    graph,
                )
            ):
                raise UserError(
                    _(
                        """Recursion error!  A product with a Bill of Material
                        should not have itself in its BoM or child BoMs!"""
                    )
                )
            V |= set([bom_line.product_id.product_tmpl_id.id])

        return new_bom_lines, (
            bom,
            {
                "qty": converted_line_quantity,
                "product": current_product,
                "original_qty": quantity,
                "parent_line": line,
            },
        )


class MrpBoMLine(models.Model):
    _inherit = "mrp.bom.line"

    factor_attribute_id = fields.Many2one(
        "product.attribute",
        string="Factor Attribute",
        help="End product attribute to use for raw material calculation",
    )
    attribute_factor = fields.Float(
        string="Factor", help="Factor to multiply by the numeric value of attribute"
    )
