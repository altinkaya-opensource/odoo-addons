##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (c) 2012-Present (<http://www.acespritech.com/>)
#    Acespritech Solutions Pvt.Ltd
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################


from odoo import api, fields, models
from odoo.tools import float_is_zero, float_round
from odoo.tools.sql import column_exists, create_column, table_exists


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def open_sales_order(self):
        self.ensure_one()
        action = self.env.ref("sale.action_orders").sudo().read()[0]
        form = self.env.ref("sale.view_order_form")
        action["views"] = [(form.id, "form")]
        action["res_id"] = self.sale_id.id
        return action

    x_durum = fields.Selection(
        [
            ("1", "İthal Eksik"),
            ("2", "CNC Kesimde"),
            ("3", "Enjeksiyonda"),
            ("4", "Montajda"),
            ("5", "Çıkacak"),
            ("6", "ACİL"),
            ("7", "Müsteriyi Bekliyor"),
            ("8", "Profil Kesimde"),
            ("9", "Sac Üretiminde"),
            ("A", "Boyada"),
            ("B", "Piyasadan Teminde"),
            ("C", "Otomatta"),
            ("D", "Rafında"),
        ],
        "Durumu",
        index=True,
    )
    hazirlayan = fields.Many2one("hr.employee", "Sevki Hazırlayan")
    operation_line_count = fields.Integer(
        string="Line Count", compute="_compute_operation_line_count", store=True
    )
    picking_total_deci = fields.Float(store=True)
    workload_deci = fields.Float(
        string="Desi", compute="_compute_workload_deci", store=True
    )
    country_id = fields.Many2one(
        "res.country",
        string="Country",
        related="partner_id.country_id",
        store=True,
    )
    partner_invoice_id = fields.Many2one(
        "res.partner",
        string="Invoice Address",
        related="sale_id.partner_invoice_id",
        store=True,
    )
    sales_uid = fields.Many2one(
        "res.users",
        string="Sales Person",
        related="sale_id.create_uid",
        store=True,
    )
    sale_note = fields.Text("Sale Note", related="sale_id.internal_note", readonly=True)
    trimmed_sale_note = fields.Text(
        compute="_compute_trimmed_sale_note",
        readonly=True,
    )

    # Convert the package_ids field to a One2many field
    package_ids = fields.One2many(
        comodel_name="stock.quant.package",
        inverse_name="picking_id",
        string="Packages",
        help="Packages related to this picking.",
        copy=True,
    )

    halted_procurements = fields.Boolean(
        store=False, search="_search_halted_procurements"
    )

    def _auto_init(self):
        if not table_exists(self.env.cr, self._table):
            return super()._auto_init()
        # Populate existing transfers in batches instead of queuing the whole table.
        for name, column_type in (
            ("operation_line_count", "int4"),
            ("picking_total_deci", "float8"),
            ("workload_deci", "float8"),
        ):
            if not column_exists(self.env.cr, self._table, name):
                create_column(self.env.cr, self._table, name, column_type)
        return super()._auto_init()

    @api.model
    def _initialize_workload_totals(self):
        """Populate newly stored fields without retaining all transfers in memory."""
        last_id = 0
        while True:
            # ORM numeric domains treat NULL and zero alike; only NULL needs backfill.
            self.env.cr.execute(
                """
                SELECT id FROM stock_picking
                 WHERE id > %s
                   AND (operation_line_count IS NULL OR picking_total_deci IS NULL
                        OR workload_deci IS NULL)
                 ORDER BY id LIMIT 1000
                """,
                [last_id],
            )
            ids = [row[0] for row in self.env.cr.fetchall()]
            if not ids:
                break
            pickings = self.browse(ids)
            pickings._compute_operation_line_count()
            pickings._compute_picking_total_deci()
            pickings._compute_workload_deci()
            self.env.invalidate_all()
            last_id = ids[-1]

    @api.depends(
        "move_ids",
        "move_ids.state",
        "move_ids.scrap_ids",
        "move_ids.package_level_id",
        "move_ids.move_line_ids.package_level_id",
        "picking_type_id.show_entire_packs",
        "immediate_transfer",
    )
    def _compute_operation_line_count(self):
        """Count product rows shown in the Operations tab, not detailed operations."""
        for picking in self:
            picking.operation_line_count = len(picking._get_move_ids_without_package())

    @api.depends(
        "move_ids.sale_line_id.last_deci",
        "move_ids.state",
        "move_ids.scrapped",
        "move_ids.product_uom_qty",
        "move_ids.quantity_done",
        "move_ids.product_uom",
        "move_ids.product_id.uom_id",
        "move_ids.product_id.weight",
        "move_ids.product_id.volume",
        "move_ids.product_id.volume_uom_id",
        "carrier_id.factor_a",
        "carrier_id.factor_b",
        "carrier_id.deci_type",
    )
    def _compute_picking_total_deci(self):
        """Use transfer quantities when the picking has no sales lines."""
        result = super()._compute_picking_total_deci()
        weight_uom = self.env[
            "product.template"
        ]._get_weight_uom_id_from_ir_config_parameter()
        kg_uom = self.env.ref("uom.product_uom_kgm")
        litre_uom = self.env.ref("uom.product_uom_litre")
        for picking in self.filtered(lambda p: not p.move_ids.sale_line_id):
            deci = 0.0
            divisor = float(picking.carrier_id.deci_type or 3000)
            for move in picking.move_ids.filtered(
                lambda m: m.state != "cancel" and not m.scrapped
            ):
                product = move.product_id
                quantity = (
                    move.quantity_done if move.state == "done" else move.product_uom_qty
                )
                quantity = move.product_uom._compute_quantity(
                    quantity, product.uom_id, round=False
                )
                weight = weight_uom._compute_quantity(
                    quantity * product.weight, kg_uom, round=False
                )
                volume = product.volume_uom_id._compute_quantity(
                    quantity * product.volume, litre_uom, round=False
                )
                deci += max(weight, volume * 1000 / divisor)
            picking.picking_total_deci = (
                deci * picking.carrier_id._get_dimension_factor(deci)
            )
        return result

    @api.depends("picking_total_weight", "picking_total_deci")
    def _compute_workload_deci(self):
        """Prefer the measured shipment value for transfer-list workload totals."""
        for picking in self:
            picking.workload_deci = (
                picking.picking_total_weight or picking.picking_total_deci
            )

    @api.model
    def _register_custom_workload_views(self):
        """Extend legacy database-only transfer lists on install and upgrade."""
        template = self.env.ref("altinkaya_stock.view_picking_tree_workload")
        views = self.env["ir.ui.view"].search(
            [
                ("model", "=", "stock.picking"),
                ("type", "=", "tree"),
                ("mode", "=", "primary"),
                ("inherit_id", "=", False),
                (
                    "name",
                    "in",
                    ["stock.picking.teslimat_tree", "stock_picking_tree_gidenkargolar"],
                ),
            ]
        )
        for view in views:
            self.env["ir.ui.view"]._load_records(
                [
                    {
                        "xml_id": f"altinkaya_stock.view_picking_workload_{view.id}",
                        "values": {
                            "name": f"{view.name}.workload",
                            "model": "stock.picking",
                            "inherit_id": view.id,
                            "arch_db": template.arch_db,
                        },
                    }
                ],
                update=True,
            )

    def _search_halted_procurements(self, operator, value):
        if operator != "=":
            return []

        ProcurementGroup = self.env["procurement.group"]
        halted_procurements = ProcurementGroup._get_halted_procurements()
        if value:
            pickings = self.search([("group_id", "in", halted_procurements.ids)])
        else:
            pickings = self.search([("group_id", "not in", halted_procurements.ids)])

        return [("id", "in", pickings.ids)]

    @api.onchange("carrier_id")
    def _onchange_carrier_id(self):
        for record in self:
            # purchase has no carrier_id field anymore
            # source = record.sale_id or record.purchase_id
            source = record.sale_id
            if record.carrier_id and source:
                source.carrier_id = record.carrier_id.id
                # source.write({"carrier_id": record.carrier_id.id})

    def _compute_trimmed_sale_note(self):
        """
        Trims the sale note to the first 50 characters.
        """
        for picking in self:
            note = (picking.sale_note or "").strip()
            if note:
                picking.trimmed_sale_note = self.env[
                    "ir.fields.converter"
                ].text_from_html(note, max_chars=50)
            else:
                picking.trimmed_sale_note = ""

    def _put_in_pack_altinkaya(self, move_lines_values, package_to_bind=None):
        package = False
        if package_to_bind:
            package = package_to_bind
        else:
            package = self.env["stock.quant.package"].create({})
        precision_digits = self.env["decimal.precision"].precision_get(
            "Product Unit of Measure"
        )

        for move_line, qty in move_lines_values.items():
            if float_is_zero(qty, precision_digits=precision_digits):
                continue

            qty_missing = float_round(
                move_line.qty_done - qty,
                precision_rounding=move_line.product_uom_id.rounding,
                rounding_method="HALF-UP",
            )

            if float_is_zero(qty_missing, precision_digits=precision_digits):
                move_line.result_package_id = package.id
            else:  # Split the move line
                # This added to work with done move lines also. Because there is
                # a restriction that reserved_uom_qty should be 0.0 in done move lines.
                if move_line.state == "done":
                    skip_reserved = True
                else:
                    skip_reserved = False

                # Bypass the restriction of updating done move lines
                move_line = move_line.with_context(
                    bypass_stock_move_update_restriction=True
                )

                # Elevate move_line environment to allow invoiced
                # move lines to be updated
                move_line = move_line.sudo()

                move_line.write(
                    {
                        "qty_done": qty,
                        "reserved_uom_qty": qty if not skip_reserved else 0.0,
                        "result_package_id": package.id,
                    }
                )
                # Create a new move line with the remaining quantity
                move_line.copy(
                    default={
                        "qty_done": qty_missing,
                        "reserved_uom_qty": qty_missing if not skip_reserved else 0.0,
                        "result_package_id": False,
                    }
                )
        return package

    def action_put_in_pack(self):
        self.ensure_one()
        return self._set_delivery_package_type()

    def action_put_packs_in_pallet(self):
        """
        This method is used to put packs in a pallet.
        It creates a new stock.quant.package record and assigns it to the move lines.
        """
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Create Pallet",
            "res_model": "wizard.create.packaging.pallet",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_picking_id": self.id,
            },
        }

    def action_see_packages(self):
        """
        Inherited to use our package_ids field instead of the Odoo's Compute
        package_ids.
        """
        res = super().action_see_packages()
        res["domain"] = [("id", "in", self.package_ids.ids)]
        return res

    def action_list_packed_products(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id(
            "stock.stock_move_line_action"
        )
        move_lines = self.move_line_ids
        action["domain"] = [("id", "in", move_lines.ids)]

        if move_lines.mapped("result_package_pallet_id"):
            group_by = ["result_package_pallet_id", "result_package_id"]
        else:
            group_by = ["result_package_id"]

        action["context"] = {"group_by": group_by}
        action["views"] = [
            (
                self.env.ref("altinkaya_stock.view_stock_move_line_tree_packaged").id,
                "tree",
            )
        ]
        return action

    def action_compute_package_numbers(self):
        """
        Compute package numbers for all packages in the picking.
        """
        for picking in self:
            picking.package_ids.action_compute_number()
            picking.package_ids.action_compute_name()
