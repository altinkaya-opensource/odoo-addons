/** @odoo-module */
import {onWillStart} from "@odoo/owl";
import {patch} from "@web/core/utils/patch";

const TranslationDialog = require("@web/views/fields/translation_dialog");

patch(TranslationDialog.TranslationDialog.prototype, "ai_translate", {
    setup() {
        this._super();

        // Owl props are read-only; keep injected state on the instance instead.
        this.aiTranslate = {company_id: null, ai_enabled: false, user_lang: false};

        onWillStart(async () => {
            const company_fields = await this._getCompanyFields();
            this.aiTranslate.user_lang = company_fields.user_lang;
            this.aiTranslate.ai_enabled = company_fields.ai_enabled;
            this.aiTranslate.company_id = company_fields.company_id;
        });
    },

    async _getCompanyFields() {
        return this.orm.call("ai.translation.config", "rpc_get_current_company_lang", []);
    },

    async onClickTranslateAll(ev) {
        if (!this.props.ai_enabled) {
            return;
        }

        const dialog = $(".o_translation_dialog");
        const rows = dialog.find(".translation");
        const translationsData = [];

        rows.each((_, row) => {
            const $row = $(row);
            const $btn = $row.find(".oe_translate_ai_btn");
            if (!$btn.length) {
                return;
            }
            const targetLang = $btn.data("lang");
            const baseLang = $btn.data("base-lang");
            const isUserLang = $btn.data("is-user-lang") === true;

            // Skip English and user's own language
            if (targetLang === "en_US" || isUserLang) {
                return;
            }
            if (!baseLang) {
                console.error("Base translation language not found for", targetLang);
                return;
            }

            const inputType = $btn.data("field-type");
            const fieldType = inputType === "textarea" ? "html" : "text";
            const $sourceInput = dialog
                .find('button[data-lang="' + baseLang + '"]')
                .closest(".translation")
                .find(inputType);
            let sourceText = $sourceInput.val();
            if (!sourceText) {
                sourceText = $row.find(".source").text();
            }

            translationsData.push({
                target_lang: targetLang,
                source_text: sourceText,
                field_type: fieldType,
            });
        });

        if (!translationsData.length) {
            return;
        }

        const $translateAllBtn = $(".oe_translate_ai_all_btn").first();
        $translateAllBtn.addClass("disabled loading");

        try {
            const result = await this.orm.call("ai.translation.config", "rpc_translate_all", [
                translationsData,
            ]);

            rows.each((_, row) => {
                const $row = $(row);
                const $btn = $row.find(".oe_translate_ai_btn");
                if (!$btn.length) {
                    return;
                }
                const targetLang = $btn.data("lang");
                const inputType = $btn.data("field-type");
                if (result[targetLang]) {
                    const $input = $row.find(inputType);
                    $input.val(result[targetLang]);
                    this.updatedTerms[$input.data("id")] = $input.val();
                    $input.css("color", "green");
                }
            });
        } catch (error) {
            console.error("Batch translation failed:", error);
        } finally {
            $translateAllBtn.removeClass("disabled loading");
        }
    },

    onClickCopyEnglish() {
        const $english = $(".o_translation_dialog")
            .find('button[data-lang="en_US"]')
            .closest(".translation")
            .find(".o_input");
        const $all_fields = $(".o_translation_dialog").find(".o_input");

        const self = this;

        $all_fields.each(function () {
            $(this).val($english.val());
            self.updatedTerms[$(this).data("id")] = $(this).val();
            $(this).css("color", "green");
        });
    },

    onClickCopyTurkish() {
        const $turkish = $(".o_translation_dialog")
            .find('button[data-lang="tr_TR"]')
            .closest(".translation")
            .find(".o_input");
        const $all_fields = $(".o_translation_dialog").find(".o_input");

        const self = this;

        $all_fields.each(function () {
            $(this).val($turkish.val());
            self.updatedTerms[$(this).data("id")] = $(this).val();
            $(this).css("color", "green");
        });
    },

    async onClickTranslate(ev) {
        const $btn = $(ev.currentTarget);
        const inputType = $btn.data("field-type");
        const fieldType = inputType === "textarea" ? "html" : "text";
        if (this.props.ai_enabled) {
            $btn.addClass("disabled loading");
            await this._translateAI($btn, inputType, fieldType);
            $btn.removeClass("disabled loading");
        }
    },

    async _translateAI($translateBtn, inputType, fieldType) {
        const target_lang = $translateBtn.data("lang");
        const source_lang = $translateBtn.data("base-lang");
        if (!source_lang) {
            console.error("Base translation language not found");
            return;
        }
        const $currentInput = $translateBtn.closest(".translation").find(inputType);
        const $source_input = $(".o_translation_dialog")
            .find('button[data-lang="' + source_lang + '"]')
            .closest(".translation")
            .find(inputType);
        let source_text = $source_input.val();
        if (!source_text) {
            source_text = $translateBtn.closest(".translation").find(".source").text();
        }

        const self = this;

        try {
            const result = await this.orm.call("ai.translation.config", "rpc_translate", [
                target_lang,
                source_text,
                fieldType,
            ]);
            if (result) {
                $currentInput.val(result);
                self.updatedTerms[$currentInput.data("id")] = $currentInput.val();
                $currentInput.css("color", "green");
            }
        } catch (error) {
            console.error("Translation failed:", error);
        }
    },
});
