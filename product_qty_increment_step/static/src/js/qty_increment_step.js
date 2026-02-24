// Copyright 2023 Yiğit Budak (https://github.com/yibudak)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

odoo.define('product_qty_increment_step.qty_step', function (require) {
    "use strict";

    var publicWidget = require('web.public.widget');
    var VariantMixin = require('sale.VariantMixin');
    var ajax = require('web.ajax');
    // Ensure WebsiteSale is loaded before we .include() it
    require('website_sale.website_sale');

    /*
     * Override onClickAddCartJSON on VariantMixin so that any widget
     * using it (including theme_prime's CartSidebar) gets step-aware
     * +/- button behavior.
     */
    VariantMixin.onClickAddCartJSON = function (ev) {
        ev.preventDefault();
        var $link = $(ev.currentTarget);
        var $span = $link.closest('.input-group').find("span[data-increment-step]");
        var $incrementSize = $span.data("increment-step");
        var minOrderQty = $span.data("min-order-qty") || 0;
        var $input = $link.closest('.input-group').find("input");

        var max = parseFloat($input.data("max") || Infinity);
        var previousQty = parseFloat($input.val() || 0, 10);
        var quantity = ($link.has(".fa-minus").length ? -$incrementSize : $incrementSize) + previousQty;
        var minQty = minOrderQty > 0 ? Math.max(minOrderQty, $incrementSize) : $incrementSize;
        var newQty = quantity > minQty ? (quantity < max ? quantity : max) : minQty;

        if (newQty !== previousQty) {
            $input.val(newQty).trigger('change');
        }
        return false;
    };

    publicWidget.registry.WebsiteSale.include({
        onClickAddCartJSON: VariantMixin.onClickAddCartJSON,

        /**
         * @override
         * After variant changes, fetch min_order_qty for the selected
         * variant and update the qty input accordingly.
         * We use our own RPC because the base _onChangeCombination callback
         * is unreachable via include due to _throttledGetCombinationInfo's
         * _.memoize + .bind closure capturing function references.
         */
        onChangeVariant: function (ev) {
            var self = this;
            this._super.apply(this, arguments);

            var $parent = $(ev.target).closest('.js_product');
            if (!$parent.length) {
                return;
            }

            var combination = this.getSelectedVariantValues($parent);
            var productTemplateId = parseInt($parent.find('.product_template_id').val());

            ajax.jsonRpc(this._getUri('/sale/get_combination_info'), 'call', {
                'product_template_id': productTemplateId,
                'product_id': this._getProductId($parent),
                'combination': combination,
                'add_qty': parseInt($parent.find('input[name="add_qty"]').val()),
                'pricelist_id': this.pricelistId || false,
            }).then(function (data) {
                self._updateMinOrderQty($parent, data);
            });
        },

        /**
         * Update min_order_qty data attribute and enforce minimum quantity
         * on the qty input based on combination info response.
         */
        _updateMinOrderQty: function ($parent, combination) {
            var minOrderQty = combination.min_order_qty || 0;
            var $span = $parent.find('.input-group span[data-increment-step]');
            if (!$span.length) {
                return;
            }
            // Only reset qty when the variant (product_id) actually changed
            var variantChanged = combination.product_id !== $span.data("last-product-id");
            $span.data("last-product-id", combination.product_id);
            $span.data("min-order-qty", minOrderQty);
            $span.attr("data-min-order-qty", minOrderQty);
            var $input = $span.closest('.input-group').find("input[name='add_qty']");
            if ($input.length) {
                var step = $span.data("increment-step") || 1;
                var minQty = minOrderQty > 0 ? Math.max(minOrderQty, step) : step;
                var currentQty = parseInt($input.val(), 10) || 0;
                if (variantChanged) {
                    $input.val(minQty);
                } else if (currentQty < minQty) {
                    $input.val(minQty);
                }
            }
        },

        /**
         * @override
         * After the default add quantity change handler, format with step.
         */
        _onChangeAddQuantity: function (ev) {
            this._super.apply(this, arguments);
            this._formatQtyWithStep(ev);
        },

        /**
         * Format the quantity with the increment step value.
         */
        _formatQtyWithStep: function (ev) {
            var $input = $(ev.currentTarget);
            var $span = $input.closest('.input-group').find("span[data-increment-step]");
            var $incrementSize = $span.data("increment-step");
            var minOrderQty = $span.data("min-order-qty") || 0;
            var minQty = minOrderQty > 0 ? Math.max(minOrderQty, $incrementSize) : $incrementSize;
            var qty = parseInt($input.val(), 10);

            if (qty === 0) {
                return false;
            }

            qty = isNaN(qty) ? minQty : qty;

            if (qty <= minQty) {
                qty = minQty;
            }

            var remainder = qty % $incrementSize;
            if (remainder > 0) {
                var prevQty = parseInt($input.data("prevQty"), 10) || minQty;
                if (qty < prevQty) {
                    qty -= remainder;
                    if (qty < minQty) {
                        qty += $incrementSize;
                    }
                } else {
                    qty += $incrementSize - remainder;
                }
            }

            $input.data("prevQty", qty);
            $input.val(qty);
        },

        /**
         * @override
         * Also format quantity with step on cart quantity change.
         */
        _onChangeCartQuantity: function (ev) {
            this._formatQtyWithStep(ev);
            this._super.apply(this, arguments);
        },
    });

});
