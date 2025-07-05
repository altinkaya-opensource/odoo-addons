/** @odoo-module **/

import { ForecastWidgetField } from "@stock/widgets/forecast_widget";
import { formatFloat } from "@web/views/fields/formatters";
import { backendUomPrecisions, UomWidgetOwl } from "./uom_widget";
import {patch} from "@web/core/utils/patch";

const { useState } = owl;

patch(ForecastWidgetField.prototype, "web_widget_uom_view_precision.ForecastWidgetField", {
    setup() {
        var res = this._super(...arguments);
        const { data, fields } = this.props.record;
        // Fetch backendUomPrecisions via jsonrpc and wait for the result
        // Use the imported backendUomPrecisions directly, don't fetch again
        this.backendUomPrecisions = backendUomPrecisions;
        this.record = useState(this.props.record);
        var field_data = this.record.activeFields[this.props.name];
        let digits = this.props.digits;
        if (field_data.widget === "uom") {
            let uom_field = field_data.options.uom_field;

            if (uom_field) {
                let uom_id = this.record.data[uom_field] && this.record.data[uom_field][0];
                let uom_precision = this.backendUomPrecisions[uom_id];
                if (uom_precision !== undefined) {
                    digits = [16, uom_precision];
                }

            }

        }
        this.reservedAvailability = formatFloat(data.reserved_availability, { digits: digits });;
        return res;
    },

});
