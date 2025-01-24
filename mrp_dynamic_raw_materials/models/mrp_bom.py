# -*- encoding: utf-8 -*-
#
#Created on Mar 5, 2018
#
#@author: dogan
#
from odoo import api, models, fields, tools, _
from odoo.exceptions import Warning as UserError
from odoo.tools.float_utils import float_round


class MrpBoM(models.Model):
    _inherit = 'mrp.bom'

#    TODO: Delete these lines after test
#     @api.v8
#     def _bom_explode(self, product, factor, properties=None, level=0,
#                      routing_id=False, previous_products=None,
#                      master_bom=None):
#         self.ensure_one()
#         bom = self
#         uom_obj = self.env["product.uom"]
#         routing_obj = self.env['mrp.routing']
#         master_bom = master_bom or bom
#         factor = self._factor(
#             factor, bom.product_efficiency, bom.product_rounding)
#         result = []
#         result2 = []
#         routing = ((routing_id and routing_obj.browse(routing_id)) or
#                    bom.routing_id or False)
#         if routing:
#             for wc_use in routing.workcenter_lines:
#                 result2.append(self._prepare_wc_line(
#                     wc_use, level=level, factor=factor))
#         for bom_line_id in bom.bom_line_ids:
#             if self._skip_bom_line(bom_line_id, product):
#                 continue
#             if (set(map(int, bom_line_id.property_ids or [])) -
#                     set(properties or [])):
#                 continue
#             product_tmpl_id = bom_line_id.product_id.product_tmpl_id.id
#             if (previous_products and
#                     product_tmpl_id in previous_products):
#                 raise UserError(
#                     _('BoM "%s" contains a BoM line with a product recursion: '
#                       '"%s".') % (master_bom.name,
#                                   bom_line_id.product_id.name_get()[0][1]))
#              
#             qty_extra = 0.0
#             if bom_line_id.factor_attribute_id:
#                 attribute_value_ids = product.attribute_value_ids
#                 attribute_value_id = attribute_value_ids.filtered(lambda v: v.attribute_id.id == bom_line_id.factor_attribute_id.id)
#                 if attribute_value_id:
#                     qty_extra = (attribute_value_id.numeric_value * bom_line_id.attribute_factor)
#              
#              
#             quantity = self._factor(
#                 (bom_line_id.product_qty + qty_extra) * factor,
#                 bom_line_id.product_efficiency, bom_line_id.product_rounding)
#             bom_id = self._bom_find_prepare(bom_line_id, properties=properties)
#             # If BoM should not behave like PhantoM, just add the product,
#             # otherwise explode further
#             if (bom_line_id.type != "phantom" and
#                     (not bom_id or self.browse(bom_id).type != "phantom")):
#                 result.append(
#                     self._prepare_consume_line(bom_line_id, quantity, factor))
#             elif bom_id:
#                 all_prod = [bom.product_tmpl_id.id] + (previous_products or [])
#                 bom2 = self.browse(bom_id)
#                 # We need to convert to units/UoM of chosen BoM
#                 factor2 = uom_obj._compute_qty(
#                     bom_line_id.product_uom.id, quantity, bom2.product_uom.id)
#                 quantity2 = factor2 / bom2.product_qty
#                 res = bom2._bom_explode(
#                     bom_line_id.product_id, quantity2, properties=properties,
#                     level=level + 10, previous_products=all_prod,
#                     master_bom=master_bom)
#                 result = result + res[0]
#                 result2 = result2 + res[1]
#             else:
#                 raise UserError(
#                     _('BoM "%s" contains a phantom BoM line but the product '
#                       '"%s" does not have any BoM defined.') %
#                     (master_bom.name, self._get_bom_product_name(bom_line_id)))
#         return result, result2



    # Overridden original method and checked factor_attribute_id field
    def explode(self, product, quantity, picking_type=False):
        """
            Explodes the BoM and creates two lists with all the information you need: bom_done and line_done
            Quantity describes the number of times you need the BoM: so the quantity divided by the number created by the BoM
            and converted into its UoM
        """
        from collections import defaultdict

        graph = defaultdict(list)
        V = set()

        def check_cycle(v, visited, recStack, graph):
            visited[v] = True
            recStack[v] = True
            for neighbour in graph[v]:
                if visited[neighbour] == False:
                    if check_cycle(neighbour, visited, recStack, graph) == True:
                        return True
                elif recStack[neighbour] == True:
                    return True
            recStack[v] = False
            return False

        boms_done = [(self, {'qty': quantity, 'product': product, 'original_qty': quantity, 'parent_line': False})]
        lines_done = []
        V |= set([product.product_tmpl_id.id])

        bom_lines = [(bom_line, product, quantity, False, "bom_line") for bom_line in self.bom_line_ids]
        # Add bom template lines
        bom_lines += [(bom_line, product, quantity, False, "tmpl_line") for bom_line in self.bom_template_line_ids]
        for bom_line in self.bom_line_ids:
            V |= set([bom_line.product_id.product_tmpl_id.id])
            graph[product.product_tmpl_id.id].append(bom_line.product_id.product_tmpl_id.id)

        # Add bom template lines
        for bom_line in self.bom_template_line_ids:
            V |= set([bom_line.product_tmpl_id.id])
            graph[product.product_tmpl_id.id].append(bom_line.product_tmpl_id.id)
        while bom_lines:
            current_line, current_product, current_qty, parent_line, line_type = bom_lines[0]
            bom_lines = bom_lines[1:]

            if current_line._skip_bom_line(current_product):
                continue
            
            # added qty_extra
            qty_extra = 0.0
            if current_line.factor_attribute_id:
                attribute_value_ids = product.attribute_value_ids
                attribute_value_id = attribute_value_ids.filtered(lambda v: v.attribute_id.id == current_line.factor_attribute_id.id)
                if attribute_value_id:
                    qty_extra = (attribute_value_id.numeric_value * current_line.attribute_factor)
            
            line_quantity = current_qty * (current_line.product_qty + qty_extra)

            if line_type == "bom_line":
                line_product = current_line.product_id
            else:
                line_product = current_line._match_possible_variant(current_product)
                if not line_product:
                    continue

            bom = self._bom_find(product=line_product, picking_type=picking_type or self.picking_type_id, company_id=self.company_id.id)

            if bom.type == 'phantom':
                converted_line_quantity = current_line.product_uom_id._compute_quantity(line_quantity / bom.product_qty, bom.product_uom_id)
                bom_lines = [(line, current_line.product_id, converted_line_quantity, current_line) for line in bom.bom_line_ids] + bom_lines
                for bom_line in bom.bom_line_ids:
                    graph[current_line.product_id.product_tmpl_id.id].append(bom_line.product_id.product_tmpl_id.id)
                    if bom_line.product_id.product_tmpl_id.id in V and check_cycle(bom_line.product_id.product_tmpl_id.id, {key: False for  key in V}, {key: False for  key in V}, graph):
                        raise UserError(_('Recursion error!  A product with a Bill of Material should not have itself in its BoM or child BoMs!'))
                    V |= set([bom_line.product_id.product_tmpl_id.id])
                boms_done.append((bom, {'qty': converted_line_quantity, 'product': current_product, 'original_qty': quantity, 'parent_line': current_line}))
            else:
                # We round up here because the user expects that if he has to consume a little more, the whole UOM unit
                # should be consumed.
                rounding = current_line.product_uom_id.rounding
                line_quantity = float_round(line_quantity, precision_rounding=rounding, rounding_method='UP')
                lines_done.append((current_line, {'target_product': line_product, 'qty': line_quantity, 'product': current_product, 'original_qty': quantity, 'parent_line': parent_line}))

        return boms_done, lines_done



class MrpBoMLine(models.Model):
    _inherit = 'mrp.bom.line'
    
    factor_attribute_id = fields.Many2one('product.attribute',string='Factor Attribute',
                                          help='End product attribute to use for raw material calculation')
    attribute_factor = fields.Float(string='Factor',help='Factor to multiply by the numeric value of attribute')

