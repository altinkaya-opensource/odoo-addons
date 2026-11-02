/** @odoo-module **/

import { CountedQuantityWidgetField } from "@stock/widgets/counted_quantity_widget";
import { ForecastWidgetField } from "@stock/widgets/forecast_widget";
import { MrpConsumed } from "@mrp/widgets/mrp_consumed";
import { MrpShouldConsumeOwl } from "@mrp/widgets/mrp_should_consume";
import { formatFloat } from "@web/views/fields/formatters";
import { getUomDigits } from "@web_widget_uom_view_precision/js/uom_widget";
import { patch } from "@web/core/utils/patch";

/**
 * These quantity widgets carry behaviour that widget="uom" would lose, so they stay
 * in place and only read the precision from their uom_field option.
 */
const uomFormattedValue = {
    get formattedValue() {
        const formatted = this._super();
        const digits = getUomDigits(this.props.record, this.props.name);
        return digits && formatted ? formatFloat(this.props.value, { digits }) : formatted;
    },
};

patch(MrpConsumed.prototype, "altinkaya_uom_views.MrpConsumed", uomFormattedValue);
patch(CountedQuantityWidgetField.prototype, "altinkaya_uom_views.CountedQuantity", uomFormattedValue);
patch(MrpShouldConsumeOwl.prototype, "altinkaya_uom_views.MrpShouldConsume", uomFormattedValue);
patch(MrpShouldConsumeOwl.prototype, "altinkaya_uom_views.MrpShouldConsumeQty", {
    get shouldConsumeQty() {
        const digits = getUomDigits(this.props.record, this.props.name);
        return digits
            ? formatFloat(this.props.record.data.should_consume_qty, { digits })
            : this._super();
    },
});
patch(ForecastWidgetField.prototype, "altinkaya_uom_views.ForecastWidget", {
    setup() {
        this._super(...arguments);
        const digits = getUomDigits(this.props.record, this.props.name);
        if (digits) {
            this.reservedAvailability = formatFloat(this.props.record.data.reserved_availability, {
                digits,
            });
        }
    },
});
