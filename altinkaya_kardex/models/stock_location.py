# Copyright 2019 Camptocamp SA
# Copyright 2026 Yiğit Budak, Altinkaya Enclosures
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class StockLocation(models.Model):
    _inherit = "stock.location"

    tray_type_id = fields.Many2one(
        comodel_name="stock.location.tray.type",
        ondelete="restrict",
        help="Set a tray type to turn this location into a Kardex tray. One child "
        "cell location is generated per grid cell.",
    )
    # Set on a cell via its parent tray. Non-empty == "I am a cell".
    cell_in_tray_type_id = fields.Many2one(
        comodel_name="stock.location.tray.type",
        string="Cell's Tray Type",
        related="location_id.tray_type_id",
        store=True,
        readonly=True,
    )
    shelf_no = fields.Integer(
        help="Human-readable shelf number of this tray. It is both the JMIF carrier "
        "the machine moves and the shelf part of every cell code (e.g. 2-0-1-61-5)."
    )
    # Grid footprint of a cell. 1x1 by default; a merged cell spans several grid slots.
    cell_cols = fields.Integer(default=1)
    cell_rows = fields.Integer(default=1)
    tray_cell_contains_stock = fields.Boolean(
        compute="_compute_tray_cell_contains_stock", store=True
    )
    # Layout fed to the tray-matrix widget (only meaningful on a tray location).
    tray_matrix = fields.Serialized(compute="_compute_tray_matrix")
    # Inverse of stock.kardex.location_id: lets is_kardex_root recompute when a
    # Kardex is (un)linked to this location.
    kardex_ids = fields.One2many(
        comodel_name="stock.kardex", inverse_name="location_id"
    )
    is_kardex_tray = fields.Boolean(
        compute="_compute_is_kardex",
        store=True,
        help="This location is a Kardex tray whose cells are auto-generated.",
    )
    is_kardex_cell = fields.Boolean(
        compute="_compute_is_kardex",
        store=True,
        help="This location is a single cell inside a Kardex tray.",
    )
    is_kardex_root = fields.Boolean(
        compute="_compute_is_kardex",
        store=True,
        help="This location is the root location of a Kardex machine.",
    )
    child_location_count = fields.Integer(compute="_compute_child_location_count")
    empty_cells = fields.Integer(
        compute="_compute_empty_cells",
        store=True,
        help="Number of empty (unoccupied) cells in this Kardex tray.",
    )
    kardex_label_line = fields.Char(
        compute="_compute_kardex_label_line",
        help="Position line for a cell's location label (empty for other locations).",
    )

    @api.depends("tray_type_id", "cell_in_tray_type_id", "kardex_ids")
    def _compute_is_kardex(self):
        for location in self:
            location.is_kardex_tray = bool(location.tray_type_id)
            location.is_kardex_cell = bool(location.cell_in_tray_type_id)
            location.is_kardex_root = bool(location.kardex_ids)

    def _compute_child_location_count(self):
        for location in self:
            location.child_location_count = len(location.child_ids)

    def action_open_child_locations(self):
        """Open the direct sub-locations of this location in a list view."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Sub-locations"),
            "res_model": "stock.location",
            "view_mode": "tree,form",
            "domain": [("location_id", "=", self.id)],
            "context": {"default_location_id": self.id},
        }

    @api.depends(
        "cell_in_tray_type_id", "posx", "posy", "cell_rows", "location_id.shelf_no"
    )
    def _compute_kardex_label_line(self):
        """Human-readable position printed on a cell's Godex label.

        Replaces the generic ``Koridor/Raf/Kat`` line, which is meaningless for a
        Kardex cell whose posx/posy are grid coordinates, not aisle/rack numbers.
        """
        for location in self:
            tray_type = location.cell_in_tray_type_id
            if not tray_type:
                location.kardex_label_line = False
                continue
            kardex = location._get_kardex()
            # A merged cell is addressed by the bottom row of its span.
            bottom_row = location.posy + (location.cell_rows or 1) - 1
            row_no = (tray_type.rows or 1) - bottom_row + 1
            cabinet = kardex.cabinet_no if kardex else ""
            shelf = location.location_id.shelf_no or ""
            # ASCII label (no Turkish chars), like the Koridor/Raf/Kat line it replaces.
            location.kardex_label_line = (
                f"Kardex:{cabinet} Tepsi:{shelf} Sira:{location.posx}-{row_no}"
            )

    @api.depends("quant_ids.quantity")
    def _compute_tray_cell_contains_stock(self):
        for location in self:
            location.tray_cell_contains_stock = any(
                q.quantity > 0 for q in location.quant_ids
            )

    @api.depends(
        "tray_type_id",
        "child_ids.active",
        "child_ids.posx",
        "child_ids.posy",
        "child_ids.cell_cols",
        "child_ids.cell_rows",
        "child_ids.tray_cell_contains_stock",
    )
    def _compute_tray_matrix(self):
        for location in self:
            tray_type = location.tray_type_id
            if not tray_type:
                location.tray_matrix = {}
                continue
            cells = location.child_ids.filtered("cell_in_tray_type_id")
            rows = tray_type.rows
            location.tray_matrix = {
                "rows": rows,
                "cols": tray_type.cols,
                "cells": [
                    {
                        "id": cell.id,
                        "x": cell.posx - 1,
                        "y": cell.posy - 1,
                        "cols": cell.cell_cols or 1,
                        "rows": cell.cell_rows or 1,
                        "occupied": cell.tray_cell_contains_stock,
                        "name": cell.name,
                        # Col-row shown in the grid; matches the label's cell address
                        # (a merged cell is addressed by the bottom row of its span).
                        "cell_ref": f"{cell.posx}-"
                        f"{rows - (cell.posy + (cell.cell_rows or 1) - 1) + 1}",
                    }
                    for cell in cells
                ],
            }

    @api.depends(
        "tray_type_id",
        "child_ids.cell_in_tray_type_id",
        "child_ids.tray_cell_contains_stock",
    )
    def _compute_empty_cells(self):
        for location in self:
            cells = location.child_ids.filtered("cell_in_tray_type_id")
            location.empty_cells = sum(
                1 for cell in cells if not cell.tray_cell_contains_stock
            )

    def _format_cell_name(self, col, row):
        """Structured location code ``depot-cabinet-shelf-col-row``.

        depot/cabinet come from the Kardex machine, the shelf from this tray, and the
        cell is addressed by its column and its row counted from the bottom (so the
        bottom cell of a column is row 01). Column and row are zero-padded to two
        digits. Missing inputs render as ``0`` until they are filled and names resync.
        """
        kardex = self._get_kardex()
        rows = self.tray_type_id.rows or 1
        row_no = rows - row + 1
        depot = kardex.depot_no if kardex else 0
        cabinet = kardex.cabinet_no if kardex else 0
        shelf = self.shelf_no or 0
        return f"{depot}-{cabinet}-{shelf}-{col:02d}-{row_no:02d}"

    def _sync_cell_names(self):
        """Rewrite child cell names after a code input changes.

        The barcode is left empty on generated cells; the name carries the code.
        """
        for tray in self.filtered("tray_type_id"):
            for cell in tray.child_ids.filtered("cell_in_tray_type_id"):
                # A merged cell is named after the bottom row of its span.
                bottom_row = cell.posy + (cell.cell_rows or 1) - 1
                new_name = tray._format_cell_name(cell.posx, bottom_row)
                if cell.name != new_name:
                    cell.write({"name": new_name})

    def _get_kardex(self):
        """Climb the parent chain to the stock.kardex this location belongs to."""
        self.ensure_one()
        kardex_model = self.env["stock.kardex"]
        node = self
        while node:
            kardex = kardex_model.search([("location_id", "=", node.id)], limit=1)
            if kardex:
                return kardex
            node = node.location_id
        return kardex_model

    def _kardex_cells(self):
        """Cell locations under this location, row-major (tray, row, col)."""
        cells = self.env["stock.location"].search(
            [("id", "child_of", self.id), ("cell_in_tray_type_id", "!=", False)]
        )
        return cells.sorted(lambda c: (c.location_id.id, c.posy, c.posx))

    def _kardex_pick_cell(self, product):
        """Cell to put ``product`` into: reuse a cell that already holds it, else
        the first empty cell, else the first cell."""
        cells = self._kardex_cells()
        same_product = cells.filtered(lambda c: product in c.quant_ids.product_id)
        if same_product:
            return same_product[:1]
        empty = cells.filtered(lambda c: not c.tray_cell_contains_stock)
        # ponytail: occupancy is by committed quants only, so a batch can co-locate
        # products in one cell. Fine for now; revisit if one-product-per-cell matters.
        return (empty or cells)[:1]

    def _get_putaway_strategy(
        self, product, quantity=0, package=None, packaging=None, additional_qty=None
    ):
        """Route a product dropped on a Kardex tray/root to a concrete cell."""
        # Cheap gate: tray is a field read; root is one indexed lookup (the root IS a
        # kardex's location, not merely under one) — no parent-chain climb on the
        # putaway hot path for ordinary locations.
        is_tray = bool(self.tray_type_id)
        is_root = not is_tray and bool(
            self.env["stock.kardex"].search_count([("location_id", "=", self.id)])
        )
        if is_tray or is_root:
            cell = self._kardex_pick_cell(product)
            if cell:
                return cell
        return super()._get_putaway_strategy(
            product,
            quantity=quantity,
            package=package,
            packaging=packaging,
            additional_qty=additional_qty,
        )

    def _generate_cells(self):
        """(Re)create one child cell location per grid cell of the tray type.

        Old cells are archived, never unlinked, so historical moves keep their source.
        """
        for tray in self.filtered("tray_type_id"):
            tray.child_ids.filtered("cell_in_tray_type_id").write({"active": False})
            tray_type = tray.tray_type_id
            posz = tray.posz or 0
            cell_vals = [
                {
                    "name": name,
                    "posx": col,
                    "posy": row,
                    "posz": posz,
                    "location_id": tray.id,
                    "usage": "internal",
                    "company_id": tray.company_id.id,
                }
                for row in range(1, tray_type.rows + 1)
                for col in range(1, tray_type.cols + 1)
                if (name := tray._format_cell_name(col, row))
            ]
            if cell_vals:
                self.create(cell_vals)

    def _check_tray_type_change(self, new_tray_type_id):
        """Guard the tray type: it can be set once, then it is immutable.

        The tray type is set only on a plain location, and once its cells are
        generated it can no longer be changed or cleared -- doing so would orphan
        the child cell locations or collide with their unique barcodes. To rework
        a tray, archive it and create a new one.
        """
        for tray in self:
            # 1. Don't convert a location that already holds arbitrary children.
            if new_tray_type_id and not tray.tray_type_id:
                foreign_children = tray.child_ids.filtered(
                    lambda c: not c.cell_in_tray_type_id
                )
                if foreign_children:
                    raise UserError(
                        _(
                            "Location %s already has sub-locations; it can't be turned "
                            "into a tray."
                        )
                        % tray.display_name
                    )
            # 2. Once cells exist, freeze the tray type (no change, no clear).
            if (
                tray.tray_type_id
                and tray.tray_type_id.id != new_tray_type_id
                and tray.child_ids.filtered("cell_in_tray_type_id")
            ):
                raise UserError(
                    _(
                        "Tray %s already has generated cells. Archive it and create a "
                        "new tray to change its type."
                    )
                    % tray.display_name
                )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._generate_cells()
        return records

    def write(self, vals):
        if "tray_type_id" in vals:
            self._check_tray_type_change(vals["tray_type_id"])
        res = super().write(vals)
        if "tray_type_id" in vals:
            self._generate_cells()
        if "shelf_no" in vals:
            self._sync_cell_names()
        return res

    def action_bring_tray(self):
        """Bring this tray to the machine opening; waits until it arrives."""
        self.ensure_one()
        kardex = self._get_kardex()
        if not kardex:
            raise UserError(_("This location is not under a Kardex."))
        if not self.shelf_no:
            raise UserError(_("Set the shelf number on tray %s first.") % self.name)
        kardex.bring_tray(str(self.shelf_no))

    def action_return_tray(self):
        """Send this tray back to storage; waits until the machine confirms."""
        self.ensure_one()
        kardex = self._get_kardex()
        if not kardex:
            raise UserError(_("This location is not under a Kardex."))
        if not self.shelf_no:
            raise UserError(_("Set the shelf number on tray %s first.") % self.name)
        kardex.return_tray(str(self.shelf_no))

    def action_merge_cells(self):
        """Merge ``self`` (a solid rectangle of empty 1x1 cells) into one cell.

        The top-left cell becomes the anchor and grows to span the rectangle, but
        it takes the bottom-left cell's code (rows are counted from the bottom, so
        the merged cell keeps the lowest code, e.g. 1-2 + 1-3 -> 1-2). The other
        cells are archived (not unlinked, so historical moves keep their source).
        """
        if len(self) < 2:
            raise UserError(_("Select at least two cells to merge."))
        tray = self.location_id
        if len(tray) != 1:
            raise UserError(_("All cells must belong to the same tray."))
        if any(c.cell_cols != 1 or c.cell_rows != 1 for c in self):
            raise UserError(_("Only 1x1 cells can be merged. Split them first."))
        if any(c.tray_cell_contains_stock for c in self):
            raise UserError(
                _("Cells that hold stock can't be merged. Empty them first.")
            )
        x1, x2 = min(self.mapped("posx")), max(self.mapped("posx"))
        y1, y2 = min(self.mapped("posy")), max(self.mapped("posy"))
        if len(self) != (x2 - x1 + 1) * (y2 - y1 + 1):
            raise UserError(_("The selection must be a solid rectangle."))
        anchor = self.filtered(lambda c: c.posx == x1 and c.posy == y1)
        anchor.write(
            {
                "cell_cols": x2 - x1 + 1,
                "cell_rows": y2 - y1 + 1,
                "name": tray._format_cell_name(x1, y2),
            }
        )
        (self - anchor).write({"active": False})
        return True

    def action_split_cell(self):
        """Split a merged cell back into 1x1 cells (reviving the archived ones)."""
        self.ensure_one()
        if self.cell_cols * self.cell_rows <= 1:
            raise UserError(_("This cell is not merged."))
        if self.tray_cell_contains_stock:
            raise UserError(
                _("A cell that holds stock can't be split. Empty it first.")
            )
        tray = self.location_id
        x1, y1 = self.posx, self.posy
        cols, rows = self.cell_cols, self.cell_rows
        # Shrinking back to 1x1 also restores the anchor's own position code
        # (it carried the bottom-left cell's code while merged).
        self.write(
            {"cell_cols": 1, "cell_rows": 1, "name": tray._format_cell_name(x1, y1)}
        )
        Cell = self.with_context(active_test=False)
        for row in range(y1, y1 + rows):
            for col in range(x1, x1 + cols):
                if col == x1 and row == y1:
                    continue
                existing = Cell.search(
                    [
                        ("location_id", "=", tray.id),
                        ("posx", "=", col),
                        ("posy", "=", row),
                    ],
                    limit=1,
                )
                if existing:
                    existing.write({"active": True, "cell_cols": 1, "cell_rows": 1})
                else:
                    name = tray._format_cell_name(col, row)
                    self.create(
                        {
                            "name": name,
                            "posx": col,
                            "posy": row,
                            "posz": tray.posz or 0,
                            "location_id": tray.id,
                            "usage": "internal",
                            "company_id": tray.company_id.id,
                        }
                    )
        return True
