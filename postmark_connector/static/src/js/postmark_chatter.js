odoo.define('postmark_connector.PostmarkMessage', function (require) {
"use strict";

var AbstractMessage = require('mail.model.AbstractMessage');

/**
 * This is a message that is handled by im_livechat, without making use of the
 * mail.Manager. The purpose of this is to make im_livechat compatible with
 * mail.widget.Thread.
 *
 * @see mail.model.AbstractMessage for more information.
 */
var PostmarkMessage =  AbstractMessage.include({

    /**
     * @param {Widget} parent
     * @param {Object} data
     * @param {string} [data.state = undefined]
     */
    init: function (parent, data) {
        this._super.apply(this, arguments);
        this._postmarkState = data.state;
    },

    getPostmarkMailState: function () {
        return this._postmarkState ? "[" + this._postmarkState + "]" : "";
    },


});

return PostmarkMessage;

});