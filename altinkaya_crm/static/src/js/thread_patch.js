/** @odoo-module **/

import { registerModel } from "@mail/model/model_core";
import { attr, one2many } from "@mail/model/model_field";

registerModel({
    name: 'mail.thread',

    fields: {
        id: attr(),
        model: attr(),
        resId: attr(),

        x_gmail_thread_id: attr({ default: "TEST-GMAIL-ID-123" }),
    },

    recordMethods: {
        getGmailUrl() {
            return this.x_gmail_thread_id
                ? `https://mail.google.com/mail/u/0/#all/${this.x_gmail_thread_id}`
                : null;
        },
    },
});
