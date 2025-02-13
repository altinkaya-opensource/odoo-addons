odoo.define('altinkaya_survey.star', function (require) {
    'use strict';

    var publicWidget = require('web.public.widget');
    var SurveyWidget = require('survey.form');

    publicWidget.registry.SurveyStarWidget = SurveyWidget.extend({
        selector: '.o_survey_form',
        events: {
            'click .fa-star-o, .fa-star': '_onStarClick'
        },

        _initializeRating: function () {
            var $star_rating = this.$('span.fa.fa-star-o, span.fa.fa-star');

            var SetRatingStar = function () {
                $star_rating.each(function () {
                    var ratingValue = parseInt($(this).siblings('input.rating-value').val());
                    if (ratingValue >= parseInt($(this).data('rating'))) {
                        $(this).removeClass('fa-star-o').addClass('fa-star');
                    } else {
                        $(this).removeClass('fa-star').addClass('fa-star-o');
                    }
                });
            };
        
            $star_rating.off('click').on('click', function () {
                if (!$(this).siblings('input.rating-value').prop('disabled')) {
                    $(this).siblings('input.rating-value').val($(this).data('rating'));
                    SetRatingStar();
                }
            });

            SetRatingStar();
        },

        _onStarClick: function (event) {
            var $target = $(event.currentTarget);
            var $input = $target.siblings('input.rating-value');
            var rating = $target.data('rating');

            if (!$input.prop('disabled')) {
                $input.val(rating);
                this._initializeRating();
            }
        },

        _prepareSubmitValues: function (formData, params) {
            this._super.apply(this, arguments);
            var self = this;
            var $form = self.$('form');
            formData = new FormData($form[0]);

            self.$('[data-question-type]').each(function () {
                var $input = $(this);
                if ($input.data('questionType') === 'star_rating') {
                    params[$input.attr('name')] = $input.val();
                }
            });
        }

    });

    return publicWidget.registry.SurveyStarWidget;
});