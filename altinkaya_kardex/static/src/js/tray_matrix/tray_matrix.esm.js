/** @odoo-module **/
/* Copyright 2026 Yiğit Budak, Altinkaya Enclosures
   License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl). */
import {Component, useState} from "@odoo/owl";

import {_lt} from "@web/core/l10n/translation";
import {registry} from "@web/core/registry";
import {standardFieldProps} from "@web/views/fields/standard_field_props";
import {useService} from "@web/core/utils/hooks";

/**
 * Renders a Kardex tray as a clickable grid where each cell is a stock.location.
 * Select a solid rectangle of empty cells and press Merge to collapse them into
 * one location; select a merged cell and press Split to break it back into 1x1s.
 */
export class KardexTrayMatrixField extends Component {
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.selection = useState({ids: []});
        // Off: a click opens the cell's location. On: a click selects for merge/split.
        this.state = useState({mergeMode: false});
    }

    get matrix() {
        return this.props.value || {rows: 0, cols: 0, cells: []};
    }

    get selectedCells() {
        return this.matrix.cells.filter((cell) => this.selection.ids.includes(cell.id));
    }

    get canMerge() {
        const selected = this.selectedCells;
        return (
            selected.length >= 2 &&
            selected.every((cell) => cell.cols === 1 && cell.rows === 1)
        );
    }

    get canSplit() {
        const selected = this.selectedCells;
        return selected.length === 1 && (selected[0].cols > 1 || selected[0].rows > 1);
    }

    isSelected(cell) {
        return this.selection.ids.includes(cell.id);
    }

    gridStyle() {
        return `grid-template-columns:repeat(${this.matrix.cols || 1},minmax(52px,1fr));`;
    }

    cellStyle(cell) {
        return (
            `grid-column:${cell.x + 1}/span ${cell.cols};` +
            `grid-row:${cell.y + 1}/span ${cell.rows};`
        );
    }

    onCellClick(cell) {
        if (this.state.mergeMode) {
            this.toggle(cell);
        } else {
            this.action.doAction({
                type: "ir.actions.act_window",
                res_model: "stock.location",
                res_id: cell.id,
                views: [[false, "form"]],
                target: "current",
            });
        }
    }

    setMergeMode(ev) {
        this.state.mergeMode = ev.target.checked;
        // Leaving merge mode drops the pending selection so it can't act later.
        if (!this.state.mergeMode) {
            this.selection.ids = [];
        }
    }

    toggle(cell) {
        const ids = this.selection.ids;
        const index = ids.indexOf(cell.id);
        if (index >= 0) {
            ids.splice(index, 1);
        } else {
            ids.push(cell.id);
        }
    }

    async _run(method) {
        // Structural edits reload the tray, so refuse over unsaved form changes.
        if (this.props.record.isDirty) {
            this.notification.add(
                _lt("Save the tray before editing its layout."),
                {type: "warning"}
            );
            return;
        }
        await this.orm.call("stock.location", method, [[...this.selection.ids]]);
        this.selection.ids = [];
        await this.props.record.load();
    }

    onMerge() {
        return this._run("action_merge_cells");
    }

    onSplit() {
        return this._run("action_split_cell");
    }
}

KardexTrayMatrixField.template = "altinkaya_kardex.KardexTrayMatrix";
KardexTrayMatrixField.props = {...standardFieldProps};
KardexTrayMatrixField.supportedTypes = ["serialized"];
KardexTrayMatrixField.displayName = _lt("Kardex tray layout");

registry.category("fields").add("kardex_tray_matrix", KardexTrayMatrixField);
