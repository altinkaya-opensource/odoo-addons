'''
Created on Nov 27, 2017

@author: dogan
'''

from odoo import models, fields, api
# from odoo.osv import fields as osv_fields
from odoo.tools.translate import _
from odoo import exceptions
from odoo.tools.misc import mute_logger

from odoo.osv.orm import browse_record

import psycopg2


class ProductMergeWizard(models.TransientModel):
    _name = 'product.merge.wizard'
    _description = 'Product Merge Wizard'

    product_tmpl_id = fields.Many2one('product.template', 'New Product Name', required=True)
    attribute_line_ids = fields.One2many('product.merge.wizard.attribute_line', 'wizard_id', string='Attributes')
    product_line_ids = fields.One2many('product.merge.wizard.product_line', 'wizard_id', string='Products')
    attribute_value_ids = fields.Many2many('product.attribute.value', 'Attribute Value IDs',
                                           compute='_compute_attribute_ids')

    @api.onchange('product_tmpl_id')
    def onchange_product_tmpl_id(self):
        self.attribute_line_ids = False
        if self.product_tmpl_id.id:
            self.attribute_line_ids = [(0, False, {'attribute_id': al.attribute_id.id,
                                                   'value_ids': [(6, False, al.value_ids.ids)]})
                                       for al in self.product_tmpl_id.attribute_line_ids]

    @api.one
    @api.depends('attribute_line_ids.value_ids')
    def _compute_attribute_ids(self):
        self.attribute_value_ids = self.attribute_line_ids.mapped('value_ids')

    @api.multi
    def action_merge(self):
        self.ensure_one()

        attribute_ids = {}
        for line in self.attribute_line_ids:
            if attribute_ids.get(line.attribute_id.id, False):
                raise exceptions.ValidationError(_('You can not add an attribute more than once'))
            attribute_ids.update({line.attribute_id.id: True})

        new_product_tmpl_id = self.product_tmpl_id  # self.product_line_ids[0].product_id.product_tmpl_id
        new_product_tmpl_id.attribute_line_ids.unlink()
        vals = {'attribute_line_ids': [(0, False, {'attribute_id': al.attribute_id.id,
                                                   'value_ids': [(6, False, al.value_ids.ids)]})
                                       for al in self.attribute_line_ids]}

        new_product_tmpl_id.with_context({'create_product_product': False}).write(vals)

        for product_line in self.product_line_ids:
            product_line.product_id.attribute_value_ids = [(6,False,product_line.value_ids.ids)]

        product_tmpl_ids = self.mapped('product_line_ids.product_id.product_tmpl_id')
        product_ids = self.mapped('product_line_ids.product_id')
        product_ids.write({'product_tmpl_id': new_product_tmpl_id.id})

        for product_tmpl_id in product_tmpl_ids:
            if product_tmpl_id.product_variant_count == 0:
                if product_tmpl_id.id != new_product_tmpl_id.id:
                    product_tmpl_id.attribute_line_ids.unlink()
                # update product references
                self._update_refs(product_tmpl_id, new_product_tmpl_id)
                product_tmpl_id.unlink()

        return {
            'name': _('Product'),
            'view_type': 'form',
            'view_mode': 'tree,form',
            'res_model': 'product.template',
            'view_id': False,
            'type': 'ir.actions.act_window',
            'domain': [('id', '=', new_product_tmpl_id.id)],
            'context': self.env.context,
        }

    @api.multi
    def _update_refs(self, product_tmpl_id, new_product_tmpl_id):
        """
        Update all references of moved product template to newly created one
        """
        self._update_foreign_keys(product_tmpl_id, new_product_tmpl_id)
        self._update_reference_fields(product_tmpl_id, new_product_tmpl_id)
        self._update_values(product_tmpl_id, new_product_tmpl_id)
        return

    @api.multi
    def get_fk_on(self, table):
        q = """  SELECT cl1.relname as table,
                        att1.attname as column
                   FROM pg_constraint as con, pg_class as cl1, pg_class as cl2,
                        pg_attribute as att1, pg_attribute as att2
                  WHERE con.conrelid = cl1.oid
                    AND con.confrelid = cl2.oid
                    AND array_lower(con.conkey, 1) = 1
                    AND con.conkey[1] = att1.attnum
                    AND att1.attrelid = cl1.oid
                    AND cl2.relname = %s
                    AND att2.attname = 'id'
                    AND array_lower(con.confkey, 1) = 1
                    AND con.confkey[1] = att2.attnum
                    AND att2.attrelid = cl2.oid
                    AND con.contype = 'f'
        """
        self.env.cr.execute(q, (table,))
        return self.env.cr.fetchall()

    @api.multi
    def _update_foreign_keys(self, product_tmpl_id, new_product_tmpl_id):

        for table, column in self.get_fk_on('product_template'):
            if 'product_merge_wizard_' in table:
                continue

            query = "SELECT column_name FROM information_schema.columns WHERE table_name LIKE '%s'" % (table)
            self.env.cr.execute(query, ())
            columns = []
            for data in self.env.cr.fetchall():
                if data[0] != column:
                    columns.append(data[0])

            query_dic = {
                'table': table,
                'column': column,
                'value': columns[0],
            }
            if len(columns) <= 1:
                # unique key treated
                query = """
                    UPDATE "%(table)s" as ___tu
                    SET %(column)s = %%s
                    WHERE
                        %(column)s = %%s AND
                        NOT EXISTS (
                            SELECT 1
                            FROM "%(table)s" as ___tw
                            WHERE
                                %(column)s = %%s AND
                                ___tu.%(value)s = ___tw.%(value)s
                        )""" % query_dic
                self.env.cr.execute(query, (new_product_tmpl_id.id, product_tmpl_id.id, new_product_tmpl_id.id))
            else:
                with mute_logger('openerp.sql_db'), self.env.cr.savepoint():
                    query = 'UPDATE "%(table)s" SET %(column)s = %%s WHERE %(column)s = %%s' % query_dic
                    self.env.cr.execute(query, (new_product_tmpl_id.id, product_tmpl_id.id,))

    @api.multi
    def _update_reference_fields(self, product_tmpl_id, new_product_tmpl_id):

        def update_records(model, src, field_model='model', field_id='res_id'):
            try:
                proxy = self.env[model].sudo()
            except KeyError:
                return

            domain = [(field_model, '=', 'product.template'), (field_id, '=', src.id)]
            ids = proxy.search(domain)
            try:
                with mute_logger('openerp.sql_db'), self.env.cr.savepoint():

                    return ids.write({field_id: new_product_tmpl_id.id})
            except psycopg2.Error:
                # updating fails, most likely due to a violated unique constraint
                # keeping record with nonexistent partner_id is useless, better delete it
                return ids.unlink()

        update_records('ir.attachment', src=product_tmpl_id, field_model='res_model')
        update_records('mail.followers', src=product_tmpl_id, field_model='res_model')
        update_records('mail.message', src=product_tmpl_id)
        update_records('ir.model.data', src=product_tmpl_id)

        proxy = self.env['ir.model.fields'].sudo()
        domain = [('ttype', '=', 'reference')]
        record_ids = proxy.search(domain)

        for record in record_ids:
            try:
                proxy_model = self.env[record.model].sudo()
                column = proxy_model._fields[record.name]
            except KeyError:
                # unknown model or field => skip
                continue

            if not column.store:
                continue

            domain = [
                (record.name, '=', 'product.template,%d' % product_tmpl_id.id)
            ]
            model_ids = proxy_model.search(domain)
            values = {
                record.name: 'product.template,%d' % new_product_tmpl_id.id,
            }
            model_ids.write(values)

    @api.multi
    def _update_values(self, product_tmpl_id, new_product_tmpl_id):
        columns = new_product_tmpl_id._fields

        def write_serializer(item):
            if isinstance(item, browse_record):
                return item.id
            else:
                return item

        values = dict()
        for column, field in columns.items():
            if isinstance(field, fields.One2many) or isinstance(field, fields.Many2many) or not field.store:
                continue
            elif not new_product_tmpl_id[column] and product_tmpl_id[column]:
                    values[column] = write_serializer(product_tmpl_id[column])

        values.pop('id', None)

        new_product_tmpl_id.write(values)


class ProductMergeAttributeLine(models.TransientModel):
    _name = 'product.merge.wizard.attribute_line'
    _description = "Product merge wizard attribute line"

    wizard_id = fields.Many2one('product.merge.wizard', string='Wizard')
    attribute_id = fields.Many2one('product.attribute', string='Attribute')
    required = fields.Boolean('Required')
    value_ids = fields.Many2many('product.attribute.value', relation='product_merge_attr_val_rel', string='Values',
                                 domain="[('attribute_id','=',attribute_id)]")


class ProductMergeProductLine(models.TransientModel):
    _name = 'product.merge.wizard.product_line'
    _description = "Product Merge Wizard Line"

    wizard_id = fields.Many2one('product.merge.wizard', string='Wizard')
    product_id = fields.Many2one('product.product', string='Product')
    value_ids = fields.Many2many('product.attribute.value', relation='product_merge_product_att_val_rel')

    @api.onchange('product_id')
    def onchange_product_id(self):
        self.value_ids = False
        attribute_value_ids = self.env['product.attribute.value']


        attribute_ids = self.wizard_id.attribute_line_ids.mapped('attribute_id')
        for value_from_product in self.product_id.attribute_value_ids:
            if value_from_product.attribute_id in attribute_ids:
                attribute_value_ids = attribute_value_ids | value_from_product
                # Eksik özellikleri yukarya eklemek çalışmadı. güncelleme yapmıyor.
                # for attribute_line in self.wizard_id.attribute_line_ids:
                #     if value_from_product.attribute_id == attribute_line.attribute_id:
                #         attribute_line.value_ids = [(6, False, (attribute_line.value_ids | value_from_product).ids)]

        self.value_ids = [(6, False, attribute_value_ids.ids)]

    @api.onchange('value_ids')
    def onchange_value_ids(self):
        existing_attribute_ids = self.value_ids.mapped('attribute_id.id')

        return {'domain': {'value_ids': [('id', 'in', self.wizard_id.attribute_line_ids.mapped('value_ids.id')),
                                         ('attribute_id', 'not in', existing_attribute_ids)]}
                }
