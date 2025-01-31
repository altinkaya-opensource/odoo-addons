// TODO: Everything in module works just fine except the survey wont get the value of star_rating. in 16.0 most of the survey logic moved to survey_form.js.
// TODO: Inherit that file and use it

odoo.define('altinkaya_survey.star', function (require) {
    'use strict';

    $(document).ready(function () {
        function initializeRating() {
            var $star_rating = $('span.fa.fa-star-o');

            var SetRatingStar = function () {
                $star_rating.each(function () {
                    if (parseInt($star_rating.siblings('input.rating-value').val()) >= parseInt($(this).data('rating'))) {
                        return $(this).removeClass('fa-star-o').addClass('fa-star');
                    } else {
                        return $(this).removeClass('fa-star').addClass('fa-star-o');
                    }
                });
            };

            $star_rating.off('click').on('click', function () {
                if (!$('.rating-value').attr('disabled')) {
                    $star_rating.siblings('input.rating-value').val($(this).data('rating'));
                    SetRatingStar();
                }
            });

            SetRatingStar();
        }


        // Initialize rating on page load
        initializeRating();

        // Re-initialize rating after AJAX updates
        $(document).ajaxComplete(function () {
            initializeRating();
        });

        // Alternatively, use Odoo's mutation observer to detect DOM changes
        if (typeof odoo !== 'undefined' && odoo.define) {
            odoo.define('altinkaya_survey.survey.star', function (require) {
                "use strict";

                $(document).ready(function () {
                    initializeRating();
                });

                $(document).ajaxComplete(function () {
                    initializeRating();
                });

                // Use mutation observer to detect DOM changes
                var observer = new MutationObserver(function (mutations) {
                    initializeRating();
                });

                // Start observing the document with the configured parameters
                observer.observe(document, { childList: true, subtree: true });
            });
        }
    });

});
