/** @odoo-module **/

import { FloatField } from "@web/views/fields/float/float_field";
import { registry } from "@web/core/registry";
import { formatFloat } from "@web/views/fields/formatters";
import rpc from "web.rpc";

// Fetch the UOM precisions from the backend
let backendUomPrecisions = {};

rpc.query({
    model: "uom.view.precision.backend",
    method: "get_uom_view_precisions",
}).then((precision_data) => {
    backendUomPrecisions = precision_data;
});

/**
 * @param {Object} record
 * @param {String} fieldName
 * @returns {Array|undefined} digits of the unit named by the field's uom_field option
 */
export function getUomDigits(record, fieldName) {
    const uomField = record.activeFields[fieldName].options.uom_field;
    const uom = uomField && record.data[uomField];
    const uomPrecision = uom ? backendUomPrecisions[uom[0]] : undefined;
    return uomPrecision === undefined ? undefined : [16, uomPrecision];
}

export class UomWidgetOwl extends FloatField {
    get formattedValue() {
        const digits = getUomDigits(this.props.record, this.props.name) || this.props.digits;
        return formatFloat(this.props.value, { digits });
    }
}

UomWidgetOwl.displayName = "UOM Widget Owl";

registry.category("fields").add("uom", UomWidgetOwl);
