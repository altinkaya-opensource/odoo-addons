/** @odoo-module **/
import {attr, one} from "@mail/model/model_field";
import {registerPatch} from "@mail/model/model_core";

registerPatch({
    name: "Message",
    modelMethods: {
        convertData(data) {
            const data2 = this._super(data);
            if ("gmail_unique_id" in data) {
                data2.gmail_unique_id = data.gmail_unique_id;
            }
            if ("gmail_thread_id" in data) {
                data2.gmail_thread_id = data.gmail_thread_id;
            }
            return data2;
        },
    },
    recordMethods: {
        hasGmailUniqueId() {
            return _.some(this.__values.get("gmail_unique_id"));
        },

        getGmailUniqueId: function () {
            if (!this.hasGmailUniqueId()) {
                return false;
            }
            return this.__values.get("gmail_unique_id");
        },

        hasGmailThreadId() {
            return _.some(this.__values.get("gmail_thread_id"));
        },

        getGmailThreadId() {
            if (!this.hasGmailThreadId()) {
                return false;
            }
            return this.__values.get("gmail_thread_id");
        },
    },
    fields: {
        gmail_unique_id: attr(),
        gmail_thread_id: attr(),
    },
});
