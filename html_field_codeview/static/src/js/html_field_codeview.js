/** @odoo-module **/
/* Copyright 2026 Yiğit Budak - ALTINKAYA
 * License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl). */
import {HtmlField} from "@web_editor/js/backend/html_field";

const superExtractProps = HtmlField.extractProps;
HtmlField.extractProps = (params) => {
    const props = superExtractProps(params);
    props.codeview = Boolean(params.attrs.options.codeview);
    return props;
};

// Core appends the code-view button to the floating wysiwyg toolbar, which is
// auto-hidden when no snippets sidebar is present (wysiwyg.js:2081-2083) and
// only appears on text selection. Move it into the .o_field_html root element
// instead — the existing CSS rule at web_editor.backend.scss:16-20 then
// absolute-positions it to the top-right corner so it is always visible.
const superStartWysiwyg = HtmlField.prototype.startWysiwyg;
HtmlField.prototype.startWysiwyg = async function (wysiwyg) {
    await superStartWysiwyg.call(this, wysiwyg);
    if (!this.props.codeview || !this.wysiwyg || !this.wysiwyg.toolbar) {
        return;
    }
    const $btnGroup = this.wysiwyg.toolbar.$el.find("#codeview-btn-group");
    if (!$btnGroup.length) {
        return;
    }
    const editable = this.wysiwyg.odooEditor && this.wysiwyg.odooEditor.editable;
    const fieldEl = editable && editable.closest && editable.closest(".o_field_html");
    if (fieldEl) {
        fieldEl.appendChild($btnGroup[0]);
    }
};
