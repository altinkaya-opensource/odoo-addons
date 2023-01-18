$(document).ready(function () {
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

    $('span.fa.fa-star-o').on('click', function () {
        if (!$('.rating-value').attr('disabled')) {
            $star_rating.siblings('input.rating-value').val($(this).data('rating'));
            SetRatingStar();
        }

    });

    $(document).ajaxComplete(function () {
        SetRatingStar();
    });

});

