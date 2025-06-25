odoo.define("altinkaya_survey.survey_result", function (require) {
    "use strict";
    var survey_print = require("survey.print");
    var publicWidget = require('web.public.widget');
    publicWidget.registry.SurveyPrintWidget = publicWidget.registry.SurveyPrintWidget.extend({
        start: function () {
            this._super.apply(this, arguments);
            this._setRatingStar(this.$('span.fa.fa-star-o'));
        },

        _setRatingStar: function ($star_rating) {
            $star_rating.each(function () {
                if (parseInt($star_rating.siblings('input.rating-value').val(), 10) >= parseInt($(this).data('rating'), 10)) {
                    return $(this).removeClass('fa-star-o').addClass('fa-star');
                }
                return $(this).removeClass('fa-star').addClass('fa-star-o');
            });
        },

    });
});
