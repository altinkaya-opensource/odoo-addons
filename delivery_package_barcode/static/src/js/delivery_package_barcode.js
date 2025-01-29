/* Copyright 2018-2019 Sergio Teruel <sergio.teruel@tecnativa.com>.
 * License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl). */

odoo.define('delivery_package_barcode.FormController', function (require) {
    'use strict';

    var FormController = require('web.FormController');

    FormController.include({
        renderButtons: function ($node) {
            /*
            Hide save and discard buttons from wizard, for this form do
            anything and confuse the user if he wants do a manual entry. All
            extended models from  wiz.stock.barcodes.read do not have this
            buttons.
            */
            this._super($node);
            if (this.modelName.includes('delivery.package.barcode.wiz')) {
                this.$buttons.find('.o_form_buttons_edit')
                    .css({'display': 'none'});
            }
        },
        canBeDiscarded: function (recordID) {
            /*
             Silent the warning that says that the record has been modified.
             */
            if (!this.modelName.includes('delivery.package.barcode.wiz')) {
                return this._super.apply(this, arguments);
            }
            return $.when(false);
        },
    });
});
