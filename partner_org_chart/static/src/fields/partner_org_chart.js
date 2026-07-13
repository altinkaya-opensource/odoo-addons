/** @odoo-module */

import { Field } from '@web/views/fields/field';
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const { Component, onWillStart, onWillRender } = owl;

export class PartnerOrgChart extends Field {
    setup() {
        super.setup();
        this.rpc = useService('rpc');
        this.orm = useService('orm');
        this.actionService = useService("action");

        onWillStart(this.handleComponentUpdate.bind(this));
        onWillRender(this.handleComponentUpdate.bind(this));
    }

    async handleComponentUpdate() {
        const partnerId = this.props.record.data.id;
        const manager = this.props.record.data.parent_id;
        const forceReload = this.lastRecord !== this.props.record || this.lastParent !== manager;
        this.lastParent = manager;
        this.lastRecord = this.props.record;
        await this.fetchPartnerData(partnerId, forceReload);
    }

    async fetchPartnerData(partnerId, force = false) {
        if (!partnerId) {
            const hadChart = this.view_partner_id;
            this.data = null;
            this.child_ids = [];
            this.view_partner_id = null;
            if (hadChart) {
                this.render(true);
            }
            return;
        }
        if (partnerId === this.view_partner_id && !force) {
            return;
        }
        this.view_partner_id = partnerId;
        const orgData = await this.rpc('/partner/get_org_chart', {
            partner_id: partnerId,
            context: Component.env.session.user_context,
        });
        this.data = orgData.data;
        this.child_ids = orgData.child_ids || [];
        this.available_roles = orgData.available_roles || [];
        this.render(true);
    }

    /**
     * Redirect to the partner form view.
     *
     * @private
     * @param {number} partnerId
     * @returns {Promise} action loaded
     */
    async _onPartnerRedirect(partnerId) {
        const action = await this.orm.call('res.partner', 'get_formview_action', [partnerId]);
        this.actionService.doAction(action);
    }

    /**
     * Archive or unarchive a contact, then refresh the chart.
     *
     * @private
     * @param {number} partnerId
     */
    async _onToggleActive(partnerId) {
        await this.orm.call('res.partner', 'toggle_active_from_org_chart', [[partnerId]]);
        await this.fetchPartnerData(this.view_partner_id, true);
    }

    /**
     * Set the storefront role of a website user, then refresh the chart.
     *
     * @private
     * @param {number} partnerId
     * @param {string} roleId  selected role id, or "" to clear
     */
    async _onChangeRole(partnerId, roleId) {
        await this.orm.write('res.partner', [partnerId], {
            website_role: roleId ? parseInt(roleId) : false,
        });
        await this.fetchPartnerData(this.view_partner_id, true);
    }
}

PartnerOrgChart.template = 'partner_org_chart.partner_org_chart';

registry.category("fields").add("partner_org_chart", PartnerOrgChart);
