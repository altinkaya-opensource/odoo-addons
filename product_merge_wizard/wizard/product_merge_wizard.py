"""
Created on Nov 27, 2017

@author: dogan
"""

import functools
import itertools
import logging
from collections import defaultdict

import psycopg2

from odoo import _, api, exceptions, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import mute_logger
from odoo.tools.misc import mute_logger

_logger = logging.getLogger(__name__)

# from odoo.osv import fields as osv_fields


class ProductMergeWizard(models.TransientModel):
    _name = "product.merge.wizard"
    _description = "Product Merge Wizard"

    product_tmpl_id = fields.Many2one(
        "product.template", "New Product Name", required=True
    )
    attribute_line_ids = fields.One2many(
        "product.merge.wizard.attribute_line", "wizard_id", string="Attributes"
    )
    product_line_ids = fields.One2many(
        "product.merge.wizard.product_line", "wizard_id", string="Products"
    )
    attribute_value_ids = fields.Many2many(
        "product.attribute.value",
        "Attribute Value IDs",
        compute="_compute_attribute_ids",
    )

    @api.onchange("product_tmpl_id")
    def onchange_product_tmpl_id(self):
        self.attribute_line_ids = False
        if self.product_tmpl_id.id:
            self.attribute_line_ids = [
                (
                    0,
                    False,
                    {
                        "attribute_id": al.attribute_id.id,
                        "value_ids": [(6, False, al.value_ids.ids)],
                    },
                )
                for al in self.product_tmpl_id.attribute_line_ids
            ]

    @api.depends("attribute_line_ids.value_ids")
    def _compute_attribute_ids(self):
        self.attribute_value_ids = self.attribute_line_ids.value_ids._origin

    def action_merge(self):
        self.ensure_one()

        # To skip computing combination_indices field.
        self = self.with_context(merging_products=True)

        attribute_ids = {}
        for line in self.attribute_line_ids:
            if attribute_ids.get(line.attribute_id.id, False):
                raise exceptions.ValidationError(
                    _("You can not add an attribute more than once")
                )
            attribute_ids.update({line.attribute_id.id: True})

        new_product_tmpl_id = (
            self.product_tmpl_id
        )  # self.product_line_ids[0].product_id.product_tmpl_id
        new_product_tmpl_id.attribute_line_ids.unlink()
        vals = {
            "attribute_line_ids": [
                (
                    0,
                    False,
                    {
                        "attribute_id": al.attribute_id.id,
                        "value_ids": [(6, False, al.value_ids.ids)],
                    },
                )
                for al in self.attribute_line_ids
            ]
        }

        new_product_tmpl_id.with_context(create_product_product=False).write(vals)

        for product_line in self.product_line_ids:
            new_attribute_values = (
                product_line.product_id.product_template_variant_value_ids.search(
                    [
                        ("product_tmpl_id", "=", new_product_tmpl_id.id),
                        (
                            "product_attribute_value_id",
                            "in",
                            product_line.value_ids.ids,
                        ),
                    ]
                )
            )
            product_line.product_id.product_template_attribute_value_ids = [
                (6, False, new_attribute_values.ids)
            ]

        product_tmpl_ids = self.mapped("product_line_ids.product_id.product_tmpl_id")
        product_ids = self.mapped("product_line_ids.product_id")
        product_ids.write({"product_tmpl_id": new_product_tmpl_id.id})

        for product_tmpl_id in product_tmpl_ids:
            if product_tmpl_id.product_variant_count == 0:
                if product_tmpl_id.id != new_product_tmpl_id.id:
                    product_tmpl_id.attribute_line_ids.unlink()
                # update product references
                self._update_refs(product_tmpl_id, new_product_tmpl_id)
                product_tmpl_id.unlink()

        return {
            "name": _("Product"),
            "view_type": "form",
            "view_mode": "tree,form",
            "res_model": "product.template",
            "view_id": False,
            "type": "ir.actions.act_window",
            "domain": [("id", "=", new_product_tmpl_id.id)],
            "context": self.env.context,
        }

    def _update_refs(self, product_tmpl_id, new_product_tmpl_id):
        """
        Update all references of moved product template to newly created one
        """
        self._update_foreign_keys(product_tmpl_id, new_product_tmpl_id)
        self._update_reference_fields(product_tmpl_id, new_product_tmpl_id)
        self._update_values(product_tmpl_id, new_product_tmpl_id)
        return

    def _get_fk_on(self, table):
        """return a list of many2one relation with the given table.
        :param table : the name of the sql table to return relations
        :returns a list of tuple 'table name', 'column name'.
        """
        query = """
            SELECT cl1.relname as table, att1.attname as column
            FROM pg_constraint as con, pg_class as cl1, pg_class as cl2, pg_attribute as att1, pg_attribute as att2
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
        self._cr.execute(query, (table,))
        return self._cr.fetchall()

    @api.model
    def _update_foreign_keys(self, src_products, dst_product):
        _logger.debug(
            "_update_foreign_keys for dst_product: %s for src_products: %s",
            dst_product.id,
            str(src_products.ids),
        )

        # find the many2one relation to a partner
        Products = self.env["product.template"]
        relations = self._get_fk_on("product_template")

        # this guarantees cache consistency
        self.env.invalidate_all()

        for table, column in relations:
            if "product_merge_wizard" in table:  # ignore two tables
                continue

            # get list of columns of current table (exept the current fk column)
            query = (
                "SELECT column_name FROM information_schema.columns WHERE table_name LIKE '%s'"
                % (table)
            )
            self._cr.execute(query, ())
            columns = []
            for data in self._cr.fetchall():
                if data[0] != column:
                    columns.append(data[0])

            # do the update for the current table/column in SQL
            query_dic = {
                "table": table,
                "column": column,
                "value": columns[0],
            }
            if len(columns) <= 1:
                # unique key treated
                query = (
                    """
                    UPDATE "%(table)s" as ___tu
                    SET "%(column)s" = %%s
                    WHERE
                        "%(column)s" = %%s AND
                        NOT EXISTS (
                            SELECT 1
                            FROM "%(table)s" as ___tw
                            WHERE
                                "%(column)s" = %%s AND
                                ___tu.%(value)s = ___tw.%(value)s
                        )"""
                    % query_dic
                )
                for partner in src_products:
                    self._cr.execute(
                        query, (dst_product.id, partner.id, dst_product.id)
                    )
            else:
                try:
                    with mute_logger("odoo.sql_db"), self._cr.savepoint():
                        query = (
                            'UPDATE "%(table)s" SET "%(column)s" = %%s WHERE "%(column)s" IN %%s'
                            % query_dic
                        )
                        self._cr.execute(
                            query,
                            (
                                dst_product.id,
                                tuple(src_products.ids),
                            ),
                        )
                except psycopg2.Error:
                    query = (
                        'DELETE FROM "%(table)s" WHERE "%(column)s" IN %%s' % query_dic
                    )
                    self._cr.execute(query, (tuple(src_products.ids),))

    @api.model
    def _update_reference_fields(self, src_products, dst_product):
        _logger.debug(
            "_update_reference_fields for dst_product: %s for src_products: %r",
            dst_product.id,
            src_products.ids,
        )

        def update_records(model, src, field_model="model", field_id="res_id"):
            Model = self.env[model] if model in self.env else None
            if Model is None:
                return
            records = Model.sudo().search(
                [(field_model, "=", "product.template"), (field_id, "=", src.id)]
            )
            try:
                with mute_logger("odoo.sql_db"), self._cr.savepoint():
                    records.sudo().write({field_id: dst_product.id})
                    records.env.flush_all()
            except psycopg2.Error:
                # updating fails, most likely due to a violated unique constraint
                # keeping record with nonexistent partner_id is useless, better delete it
                records.sudo().unlink()

        update_records = functools.partial(update_records)

        for product in src_products:
            update_records("ir.attachment", src=product, field_model="res_model")
            update_records("mail.followers", src=product, field_model="res_model")
            update_records("mail.activity", src=product, field_model="res_model")
            update_records("mail.message", src=product)
            update_records("ir.model.data", src=product)

        records = (
            self.env["ir.model.fields"].sudo().search([("ttype", "=", "reference")])
        )
        for record in records:
            try:
                Model = self.env[record.model]
                field = Model._fields[record.name]
            except KeyError:
                # unknown model or field => skip
                continue

            if Model._abstract or field.compute is not None:
                continue

            for product in src_products:
                records_ref = Model.sudo().search(
                    [(record.name, "=", "product.template,%d" % product.id)]
                )
                values = {
                    record.name: "product.template,%d" % dst_product.id,
                }
                records_ref.sudo().write(values)

        self.env.flush_all()

    @api.model
    def _update_values(self, src_products, dst_product):
        _logger.debug(
            "_update_values for dst_product: %s for src_products: %r",
            dst_product.id,
            src_products.ids,
        )

        model_fields = dst_product.fields_get().keys()

        def write_serializer(item):
            if isinstance(item, models.BaseModel):
                return item.id
            else:
                return item

        # get all fields that are not computed or x2many
        values = dict()
        for column in model_fields:
            field = dst_product._fields[column]
            if field.type not in ("many2many", "one2many") and field.compute is None:
                for item in itertools.chain(src_products, [dst_product]):
                    if item[column]:
                        values[column] = write_serializer(item[column])

        # remove fields that can not be updated (id and parent_id)
        values.pop("id", None)
        dst_product.write(values)


class ProductMergeAttributeLine(models.TransientModel):
    _name = "product.merge.wizard.attribute_line"
    _description = "Product merge wizard attribute line"

    wizard_id = fields.Many2one("product.merge.wizard", string="Wizard")
    attribute_id = fields.Many2one("product.attribute", string="Attribute")
    required = fields.Boolean()
    value_ids = fields.Many2many(
        "product.attribute.value",
        string="Values",
        domain="[('attribute_id','=',attribute_id)]",
    )


class ProductMergeProductLine(models.TransientModel):
    _name = "product.merge.wizard.product_line"
    _description = "Product Merge Wizard Line"

    wizard_id = fields.Many2one("product.merge.wizard", string="Wizard")
    product_id = fields.Many2one("product.product", string="Product")
    possible_value_ids = fields.Many2many(
        "product.attribute.value",
        relation="product_merge_possible_value_ids_rel",
        string="Possible Values",
    )
    value_ids = fields.Many2many(
        "product.attribute.value",
        relation="product_merge_value_ids_rel",
    )

    @api.onchange("product_id")
    def onchange_product_id(self):
        value_ids = self.wizard_id.attribute_line_ids.value_ids
        self.possible_value_ids = [(6, False, value_ids.ids)]

    @api.onchange("possible_value_ids")
    def onchange_value_ids(self):
        return {
            "domain": {
                "value_ids": [
                    (
                        "id",
                        "in",
                        self.possible_value_ids.ids,
                    ),
                ]
            }
        }
