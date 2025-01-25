#
# Created on Mar 5, 2018
#
# @author: dogan
#
from collections import defaultdict

from odoo import _, fields, models
from odoo.exceptions import Warning as UserError
from odoo.tools.float_utils import float_round


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

    def explode(self, product, quantity, picking_type=False):
        graph = defaultdict(list)
        V = set([product.product_tmpl_id.id])

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

        bom_lines = [
            (line, product, quantity, False, "bom_line") for line in self.bom_line_ids
        ]
        bom_lines += [
            (line, product, quantity, False, "tmpl_line")
            for line in self.bom_template_line_ids
        ]

        for bom_line in self.bom_line_ids:
            V |= set([bom_line.product_id.product_tmpl_id.id])
            graph[product.product_tmpl_id.id].append(
                bom_line.product_id.product_tmpl_id.id
            )

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

            line_quantity = self._compute_line_quantity(
                current_line, current_product, current_qty
            )
            line_product = (
                current_line.product_id
                if line_type == "bom_line"
                else current_line._match_possible_variant(current_product)
            )

            if not line_product and line_type != "bom_line":
                continue

            bom = self._bom_find(
                products=line_product,
                picking_type=picking_type or self.picking_type_id,
                company_id=self.company_id.id,
            )

            if bom.type == "phantom":
                new_lines, new_bom = self._process_phantom_bom(
                    bom,
                    current_line,
                    line_quantity,
                    current_product,
                    quantity,
                    graph,
                    V,
                )
                bom_lines = new_lines + bom_lines
                boms_done.append(new_bom)
            else:
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
