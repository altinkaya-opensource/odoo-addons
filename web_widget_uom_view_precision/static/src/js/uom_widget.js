/** @odoo-module **/

import { FloatField } from "@web/views/fields/float/float_field";
import { registry } from "@web/core/registry";
import { formatFloat } from "@web/views/fields/formatters";
import rpc from "web.rpc";

const { useState } = owl;

// Fetch the UOM precisions from the backend
let backendUomPrecisions = {};

rpc.query({
    model: "uom.view.precision.backend",
    method: "get_uom_view_precisions",
}).then((precision_data) => {
    backendUomPrecisions = precision_data;
});

export class UomWidgetOwl extends FloatField {
    setup() {
        super.setup();
        this.backendUomPrecisions = backendUomPrecisions;
        this.record = useState(this.props.record);
    }


    get formattedValue() {
        var field_data = this.record.activeFields[this.props.name];
        let digits = this.props.digits;
        if (field_data.widget === "uom") {
            let uom_field = field_data.options.uom_field;

            if (uom_field) {
                let uom_id = this.record.data["product_uom"] && this.record.data["product_uom"][0];
                let uom_precision = this.backendUomPrecisions[uom_id];
                if (uom_precision !== undefined) {
                    digits = [16, uom_precision];
                }

            }

        }
        return formatFloat(this.props.value, { digits: digits });
    }
}

UomWidgetOwl.displayName = "UOM Widget Owl";

registry.category("fields").add("uom", UomWidgetOwl);
