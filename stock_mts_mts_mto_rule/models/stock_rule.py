# Copyright 2022 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from odoo.tools import float_compare, float_is_zero


class StockRule(models.Model):
    _inherit = 'stock.rule'

    action = fields.Selection(
        selection_add=[('split_procurement2', 'MTS+MTS+MTO')])
    mts2_rule_id = fields.Many2one(
        'stock.rule', string="MTS2 Rule")

    @api.constrains('action', 'mts2_rule_id')
    def _check_mts_mto_rule(self):
        for rule in self:
            if rule.action == 'split_procurement2':
                if not rule.mts_rule_id or not rule.mto_rule_id or not rule.mts2_rule_id:
                    msg = _('No MTS or MTO rule configured on procurement '
                            'rule: %s!') % (rule.name, )
                    raise ValidationError(msg)
                if (rule.mts_rule_id.location_src_id.id ==
                        rule.mts2_rule_id.location_src_id.id):
                    msg = _('Inconsistency between the source locations of '
                            'the mts and mts2 rules linked to the procurement '
                            'rule: %s! It should not be the same.') % (rule.name,)
                    raise ValidationError(msg)

    @api.multi
    def get_mto_qty_to_order2(self, product, product_qty, product_uom, values):
        self.ensure_one()
        precision = self.env['decimal.precision']\
            .precision_get('Product Unit of Measure')
        src_location_id = self.mts2_rule_id.location_src_id.id
        product_location = product.with_context(location=src_location_id)
        qty_available = self._get_qty_available_for_mto_qty(
            product, product_location, product_uom)

        if float_compare(qty_available, 0.0, precision_digits=precision) > 0:
            if float_compare(qty_available, product_qty,
                             precision_digits=precision) >= 0:
                return 0.0
            else:
                return product_qty - qty_available
        return product_qty

    def _run_split_procurement2(self, product_id, product_qty, product_uom,
                               location_id, name, origin, values):
        precision = self.env['decimal.precision']\
            .precision_get('Product Unit of Measure')
        needed_qty = self.get_mto_qty_to_order(product_id, product_qty,
                                               product_uom, values)

        if (((product_qty - needed_qty) / product_qty) * 100) < (self.do_not_split_percentage or 0.0):
            needed_qty = product_qty

        if float_is_zero(needed_qty, precision_digits=precision):
            getattr(self.mts_rule_id, '_run_%s' % self.mts_rule_id.action)(
                product_id, product_qty, product_uom, location_id, name,
                origin, values)
        elif float_compare(needed_qty, product_qty,
                           precision_digits=precision) == 0.0:
            getattr(self.mto_rule_id, '_run_%s' % self.mto_rule_id.action)(
                product_id, product_qty, product_uom, location_id, name,
                origin, values)
        else:
            mts_qty = product_qty - needed_qty
            getattr(self.mts_rule_id, '_run_%s' % self.mts_rule_id.action)(
                product_id, mts_qty, product_uom, location_id, name, origin,
                values)
            getattr(self.mto_rule_id, '_run_%s' % self.mto_rule_id.action)(
                product_id, needed_qty, product_uom, location_id, name,
                origin, values)
        return True
