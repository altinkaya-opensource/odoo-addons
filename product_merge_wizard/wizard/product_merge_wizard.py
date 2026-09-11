"""
Created on Nov 27, 2017

@author: dogan
"""

import functools
import logging

import psycopg2

from odoo import Command, _, api, exceptions, fields, models
from odoo.tools import mute_logger

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
        target_template = self.product_tmpl_id
        product_values = self._validate_merge()
        products = self.product_line_ids.product_id
        source_templates = products.product_tmpl_id - target_template

        target_values = self._prepare_target_attribute_values()
        merging_products = products.with_context(merging_products=True)
        for product in products:
            product.with_context(merging_products=True).write(
                {
                    "product_template_attribute_value_ids": [
                        Command.set(
                            [
                                target_values[value.id].id
                                for value in product_values[product.id]
                            ]
                        )
                    ]
                }
            )

        # NULL indices allow valid combination swaps within one transaction.
        # They are recomputed with the normal Odoo implementation below.
        merging_products._compute_combination_indices()
        merging_products.flush_recordset(["combination_indices"])
        merging_products.write({"product_tmpl_id": target_template.id})
        self._prune_target_attribute_values()
        products._compute_combination_indices()
        products.flush_recordset(["combination_indices", "product_tmpl_id"])

        for source_template in source_templates:
            source_template.invalidate_recordset(["product_variant_ids"])
            if not source_template.with_context(active_test=False).product_variant_ids:
                self._update_refs(source_template, target_template)
                source_template.unlink()

        return {
            "name": _("Product"),
            "view_type": "form",
            "view_mode": "tree,form",
            "res_model": "product.template",
            "view_id": False,
            "type": "ir.actions.act_window",
            "domain": [("id", "=", target_template.id)],
            "context": self.env.context,
        }

    def _get_attribute_configuration(self):
        configuration = {}
        for line in self.attribute_line_ids:
            if not line.attribute_id or not line.value_ids:
                raise exceptions.ValidationError(
                    _("Every attribute must have at least one value.")
                )
            if line.attribute_id.id in configuration:
                raise exceptions.ValidationError(
                    _("You can not add an attribute more than once")
                )
            if line.value_ids.attribute_id != line.attribute_id:
                raise exceptions.ValidationError(
                    _("Every value must belong to its attribute.")
                )
            configuration[line.attribute_id.id] = line.value_ids
        return configuration

    def _validate_merge(self):
        configuration = self._get_attribute_configuration()
        if not self.product_line_ids:
            raise exceptions.ValidationError(_("Select at least one product to merge."))

        products = self.product_line_ids.product_id
        if len(products) != len(self.product_line_ids):
            raise exceptions.ValidationError(
                _("You can not add a product more than once.")
            )

        target_configuration = {
            line.attribute_id.id: frozenset(line.value_ids.ids)
            for line in self.product_tmpl_id.attribute_line_ids
        }
        requested_configuration = {
            attribute_id: frozenset(values.ids)
            for attribute_id, values in configuration.items()
        }
        target_products = self.product_tmpl_id.with_context(
            active_test=False
        ).product_variant_ids.filtered("active")
        if target_configuration != requested_configuration:
            missing_target_products = target_products - products
            if missing_target_products:
                raise exceptions.ValidationError(
                    _(
                        "Add every active variant of the target product when changing "
                        "its attributes. Missing: %(products)s",
                        products=", ".join(
                            missing_target_products.mapped("display_name")
                        ),
                    )
                )

        variant_attribute_ids = {
            attribute_id
            for attribute_id in configuration
            if self.env["product.attribute"].browse(attribute_id).create_variant
            != "no_variant"
        }
        configured_value_ids = {
            value.id for values in configuration.values() for value in values
        }
        product_values = {}
        combinations = {}

        for product_line in self.product_line_ids:
            values = product_line.value_ids
            selected_attribute_ids = set(values.attribute_id.ids)
            if (
                not set(values.ids) <= configured_value_ids
                or selected_attribute_ids != variant_attribute_ids
                or any(
                    len(values.filtered(lambda value: value.attribute_id.id == attr_id))
                    != 1
                    for attr_id in variant_attribute_ids
                )
            ):
                raise exceptions.ValidationError(
                    _(
                        "Select exactly one configured value for every variant "
                        "attribute of %(product)s.",
                        product=product_line.product_id.display_name,
                    )
                )
            product_values[product_line.product_id.id] = values
            self._register_combination(
                combinations, frozenset(values.ids), product_line.product_id
            )

        for product in target_products - products:
            values = product.product_template_attribute_value_ids.mapped(
                "product_attribute_value_id"
            )
            self._register_combination(combinations, frozenset(values.ids), product)

        return product_values

    def _register_combination(self, combinations, combination, product):
        if combination in combinations:
            raise exceptions.ValidationError(
                _(
                    "%(first)s and %(second)s have the same attribute combination.",
                    first=combinations[combination].display_name,
                    second=product.display_name,
                )
            )
        combinations[combination] = product

    def _prepare_target_attribute_values(self):
        configuration = self._get_attribute_configuration()
        target_template = self.product_tmpl_id.with_context(merging_products=True)
        lines_by_attribute = {
            line.attribute_id.id: line for line in target_template.attribute_line_ids
        }
        AttributeLine = self.env["product.template.attribute.line"].with_context(
            merging_products=True
        )

        for attribute_id, values in configuration.items():
            line = lines_by_attribute.get(attribute_id)
            if line:
                additive_values = line.value_ids | values
                if additive_values != line.value_ids:
                    line.write({"value_ids": [Command.set(additive_values.ids)]})
            else:
                AttributeLine.create(
                    {
                        "product_tmpl_id": target_template.id,
                        "attribute_id": attribute_id,
                        "value_ids": [Command.set(values.ids)],
                    }
                )

        self.env.flush_all()
        target_template.invalidate_recordset(["attribute_line_ids"])
        target_values = (
            target_template.attribute_line_ids.product_template_value_ids.filtered(
                "ptav_active"
            )
        )
        values_by_id = {
            value.product_attribute_value_id.id: value for value in target_values
        }
        missing_values = set().union(
            *(set(values.ids) for values in configuration.values())
        ) - set(values_by_id)
        if missing_values:
            raise exceptions.ValidationError(
                _("The target product attribute values could not be created.")
            )
        return values_by_id

    def _prune_target_attribute_values(self):
        configuration = self._get_attribute_configuration()
        target_template = self.product_tmpl_id.with_context(merging_products=True)
        target_template.invalidate_recordset(["attribute_line_ids"])
        for line in target_template.attribute_line_ids:
            values = configuration.get(line.attribute_id.id)
            if values is None:
                line.unlink()
            elif line.value_ids != values:
                line.write({"value_ids": [Command.set(values.ids)]})

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
        relations = self._get_fk_on("product_template")

        # this guarantees cache consistency
        self.env.invalidate_all()

        for table, column in relations:
            if "product_merge_wizard" in table:  # ignore two tables
                continue

            # get list of columns of current table (exept the current fk column)
            query = (
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name LIKE %s"
            )
            self._cr.execute(query, tuple([table]))
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
                query = """
                    UPDATE "{table}" as ___tu
                    SET "{column}" = %s
                    WHERE
                        "{column}" = %s AND
                        NOT EXISTS (
                            SELECT 1
                            FROM "{table}" as ___tw
                            WHERE
                                "{column}" = %s AND
                                ___tu.{value} = ___tw.{value}
                        )""".format(**query_dic)
                for partner in src_products:
                    self._cr.execute(
                        query, (dst_product.id, partner.id, dst_product.id)
                    )
            else:
                try:
                    with mute_logger("odoo.sql_db"), self._cr.savepoint():
                        query = (
                            'UPDATE "%(table)s" SET "%(column)s" = %%s WHERE "%(column)s" IN %%s'  # noqa
                            % query_dic
                        )
                        self._cr.execute(
                            query,
                            (
                                dst_product.id,
                                tuple(src_products.ids),
                            ),
                        )
                except psycopg2.Error as error:
                    raise exceptions.UserError(
                        _(
                            "The references in %(table)s.%(column)s could not be "
                            "moved safely.",
                            table=table,
                            column=column,
                        )
                    ) from error

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
            for record in records:
                try:
                    with mute_logger("odoo.sql_db"), self._cr.savepoint():
                        record = record.sudo()
                        record.write({field_id: dst_product.id})
                        record.flush_recordset([field_id])
                except psycopg2.Error as error:
                    raise exceptions.UserError(
                        _(
                            "A %(model)s reference could not be moved safely.",
                            model=model,
                        )
                    ) from error

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
                    [(record.name, "=", f"product.template,{product.id}")]
                )
                values = {
                    record.name: f"product.template,{dst_product.id}",
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

        # Fill only empty target fields. Rewriting values such as ``active``
        # can trigger unrelated product-template side effects.
        values = dict()
        for column in model_fields:
            field = dst_product._fields[column]
            if (
                field.type in ("many2many", "one2many")
                or field.compute is not None
                or dst_product[column]
            ):
                continue
            for item in src_products:
                if item[column]:
                    values[column] = write_serializer(item[column])

        # Remove fields that can not be updated.
        values.pop("id", None)
        if values:
            dst_product.with_context(merging_products=True).write(values)


class ProductMergeAttributeLine(models.TransientModel):
    _name = "product.merge.wizard.attribute_line"
    _description = "Product merge wizard attribute line"

    wizard_id = fields.Many2one("product.merge.wizard")
    attribute_id = fields.Many2one("product.attribute")
    required = fields.Boolean()
    value_ids = fields.Many2many(
        "product.attribute.value",
        string="Values",
        domain="[('attribute_id','=',attribute_id)]",
    )


class ProductMergeProductLine(models.TransientModel):
    _name = "product.merge.wizard.product_line"
    _description = "Product Merge Wizard Line"

    wizard_id = fields.Many2one("product.merge.wizard")
    product_id = fields.Many2one("product.product")
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
