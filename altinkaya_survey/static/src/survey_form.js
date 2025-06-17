odoo.define("altinkaya_survey.survey_form", function (require) {
    "use strict";
    var survey_form = require("survey.form");
    var publicWidget = require('web.public.widget');

    publicWidget.registry.SurveyFormWidget = publicWidget.registry.SurveyFormWidget.extend({

        events: _.extend({}, publicWidget.registry.SurveyFormWidget.prototype.events, {
            'click span.fa.fa-star-o': '_onStarRatingClick',
            'click span.fa.fa-star': '_onStarRatingClick',
        }),

        start: function () {
            this._super.apply(this, arguments);
        },

        _prepareSubmitValues: function (formData, params) {
            var values = this._super.apply(this, arguments);
            this.$('[data-question-type]').each(function () {
                switch ($(this).data('questionType')) {
                    case 'star_rating':
                        params[this.name] = this.value;
                        break;

                }
            });
            return values;
        },

        _onStarRatingClick: function (ev) {
            const $ev = $(ev.currentTarget);
            if (!$('.rating-value').attr('disabled')) {
                $ev.siblings(`input.rating-value`).val($ev.data(`rating`));
                this._setRatingStar();
            }
        },

        _setRatingStar: function () {
            const $star_rating = $('span.fa.fa-star-o, span.fa.fa-star');
            $star_rating.each(function () {
                if (parseInt($star_rating.siblings('input.rating-value').val(), 10) >= parseInt($(this).data('rating'), 10)) {
                    return $(this).removeClass('fa-star-o').addClass('fa-star');
                }
                return $(this).removeClass('fa-star').addClass('fa-star-o');
            });
        },

    });
});
