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
    def _calculate_qtys_mts_mts_mto(self, product, product_qty, product_uom, values):
        self.ensure_one()
        precision = self.env['decimal.precision']\
            .precision_get('Product Unit of Measure')
        src_location_id1 = self.mts_rule_id.location_src_id.id
        src_location_id2 = self.mts2_rule_id.location_src_id.id

        product_location1 = product.with_context(location=src_location_id1)
        product_location2 = product.with_context(location=src_location_id2)

        qty_available = self._get_qty_available_for_mto_qty(
            product, product_location1, product_uom)

        if ((qty_available / product_qty) * 100) < (self.do_not_split_percentage or 0.0):
            qty_available = 0.0

        if float_compare(qty_available, product_qty, precision_digits=precision) < 0:
            qty_available2 = self._get_qty_available_for_mto_qty(
                product, product_location2, product_uom)

            if ((qty_available2 / product_qty) * 100) < (self.do_not_split_percentage or 0.0):
                qty_available2 = 0.0

        else:
            qty_available2 = 0.0

        total_qty_available = qty_available + qty_available2

        if float_compare(total_qty_available, 0.0, precision_digits=precision) > 0:
            if float_compare(total_qty_available, product_qty,
                             precision_digits=precision) >= 0:
                return qty_available, qty_available2, 0.0
            else:
                return qty_available, qty_available2, product_qty - total_qty_available
        return qty_available, qty_available2, product_qty

    def _run_split_procurement2(self, product_id, product_qty, product_uom,
                               location_id, name, origin, values):
        precision = self.env['decimal.precision']\
            .precision_get('Product Unit of Measure')
        mts1_qty, mts2_qty, mto_qty = self._calculate_qtys_mts_mts_mto(product_id, product_qty,
                                               product_uom, values)

        """
            MTS1   MTS2   MTO
        1)  100      0      0
        2)  50       50     0
        3)  50       0      50
        4)  0        100    0
        5)  0        50     50
        6)  0        0      100
        """

        if float_is_zero(mto_qty, precision_digits=precision):
            if float_is_zero(mts2_qty, precision_digits=precision):  # 1
                getattr(self.mts_rule_id, '_run_%s' % self.mts_rule_id.action)(
                    product_id, product_qty, product_uom, location_id, name,
                    origin, values)
            elif float_is_zero(mts1_qty, precision_digits=precision):  # 4
                getattr(self.mts2_rule_id, '_run_%s' % self.mts2_rule_id.action)(
                    product_id, product_qty, product_uom, location_id, name,
                    origin, values)

            else:  # 2
                getattr(self.mts_rule_id, '_run_%s' % self.mts_rule_id.action)(
                    product_id, mts1_qty, product_uom, location_id, name,
                    origin, values)
                if not float_is_zero(mts2_qty, precision_digits=precision):
                    getattr(self.mts2_rule_id, '_run_%s' % self.mts2_rule_id.action)(
                        product_id, mts2_qty, product_uom, location_id, name,
                        origin, values)

        else:
            if float_is_zero(mts1_qty+mts2_qty, precision_digits=precision):  # 6
                getattr(self.mto_rule_id, '_run_%s' % self.mto_rule_id.action)(
                    product_id, mto_qty, product_uom, location_id, name,
                    origin, values)

            elif float_is_zero(mts2_qty, precision_digits=precision):  # 3
                getattr(self.mts_rule_id, '_run_%s' % self.mts_rule_id.action)(
                    product_id, (product_qty - mto_qty), product_uom, location_id, name, origin,
                    values)
                getattr(self.mto_rule_id, '_run_%s' % self.mto_rule_id.action)(
                    product_id, mto_qty, product_uom, location_id, name,
                    origin, values)

            else:  # 5
                getattr(self.mts2_rule_id, '_run_%s' % self.mts2_rule_id.action)(
                    product_id, (product_qty - mto_qty), product_uom, location_id, name, origin,
                    values)
                getattr(self.mto_rule_id, '_run_%s' % self.mto_rule_id.action)(
                    product_id, mto_qty, product_uom, location_id, name,
                    origin, values)

        return True
