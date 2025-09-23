// Copyright (C) 2025 Ahmet Yiğit Budak (https://github.com/yibudak)
odoo.define('payment_iyzico_altinkaya.payment_form', require => {
    'use strict';

    const core = require('web.core');
    const checkoutForm = require('payment.checkout_form');
    const manageForm = require('payment.manage_form');
    const rpc = require('web.rpc');
    var field_utils = require('web.field_utils');
    const sprintf = require('web.utils').sprintf;
    const _t = core._t;

    const paymentiyzicoMixin = {
        /**
         * Lifecycle
         */
        /**
         * Initialize the payment form mixin.
         * @returns {Promise} Promise resolving when initialization is complete.
         */
        start: function () {
            const res = this._super ? this._super(...arguments) : Promise.resolve();
            this._installmentDebounceTimer = null;
            this._lastCardNumber = null;
            this._debouncedLoadInstallments = this._debounce(
                this._loadInstallmentOptions.bind(this),
                250
            );
            this._bindCardFormatterAndInstallmentLoader();
            this._bindInstallmentSelectionHandlers();
            this._iyzicoInstallmentEnabled = $("#iyzico-form [name='iyzico_installment_enabled']").val() === 'True';
            return res;
        },

        /**
         * Utils
         */
        /**
         * Create a debounced version of a function.
         * @param {Function} func - The function to debounce.
         * @param {number} delay - The delay in milliseconds.
         * @returns {Function} The debounced function.
         */
        _debounce: function (func, delay) {
            return (...args) => {
                clearTimeout(this._installmentDebounceTimer);
                this._installmentDebounceTimer = setTimeout(() => func(...args), delay);
            };
        },

        /**
         * Convert a base64 string to UTF-8.
         * @param {string} b64 - The base64 encoded string.
         * @returns {string} The decoded UTF-8 string.
         */
        _base64ToUtf8: function (b64) {
            const bin = atob(b64);
            const bytes = Uint8Array.from(bin, c => c.charCodeAt(0));
            return new TextDecoder().decode(bytes);
        },

        /**
         * DOM bindings
         */
        /**
         * Bind card number formatting and installment loading handlers.
         */
        _bindCardFormatterAndInstallmentLoader: function () {
            const $input = $("#iyzico-form [name='cardNumber']");
            $input
                .off('keydown.iyzico input.iyzico')
                .on('keydown.iyzico', function (e) {
                    const cursor = this.selectionStart;
                    if (this.selectionEnd !== cursor) return;
                    if (e.which === 46) {
                        if (this.value[cursor] === ' ') this.selectionStart++;
                    } else if (e.which === 8) {
                        if (cursor && this.value[cursor - 1] === ' ') this.selectionEnd--;
                    }
                })
                .on('input.iyzico', (e) => {
                    const el = e.currentTarget;
                    let value = el.value;

                    if (this._iyzicoInstallmentEnabled) {
                        const $installmentsSection = $('#iyzico-installments');
                        const $installmentInfoText = $('#installment-info-text');
                        const $container = $('#installment-options-container');
                        if (value.replace(/\D/g, '').length >= 8) {
                            if ($installmentsSection.hasClass('d-none')) {
                                $installmentsSection.removeClass('d-none');
                                $('#installment-title').text(_t('Installment Options'));
                                $('#installment-subtitle').text(_t('Choose the installment option that suits your card'));
                            }
                            $container.find('.iyzico-installment-option, .alert').remove();
                            if ($container.find('.iyzico-loading').length === 0) {
                                $container.append(`
                                    <div class="iyzico-loading text-center p-4">
                                        <div class="spinner-border spinner-border-sm me-2" role="status">
                                            <span class="visually-hidden">${_t('Loading...')}</span>
                                        </div>
                                        ${_t('Loading installment options...')}
                                    </div>
                                `);
                            }
                            $installmentInfoText.addClass('d-none');
                            this._debouncedLoadInstallments(value.replace(/\D/g, ''));
                        } else {
                            $installmentsSection.addClass('d-none');
                            $installmentInfoText.removeClass('d-none');
                            // reset
                            $container.find('.iyzico-installment-option, .iyzico-loading, .alert').remove();
                        }
                    }


                    // format as 4-4-4-4
                    let cursor = el.selectionStart;
                    const pre = value.substring(0, cursor);
                    const nonDigitsBefore = pre.match(/[^0-9]/g);
                    if (nonDigitsBefore) cursor -= nonDigitsBefore.length;

                    value = value.replace(/[^0-9]/g, '').substring(0, 16);
                    let formatted = '';
                    for (let i = 0; i < value.length; i++) {
                        if (i && i % 4 === 0) {
                            if (formatted.length <= cursor) cursor++;
                            formatted += ' ';
                        }
                        formatted += value[i];
                    }
                    if (formatted === el.value) return;
                    el.value = formatted;
                    el.selectionEnd = cursor;
                });
        },

        /**
         * Bind handlers for installment option selection.
         */
        _bindInstallmentSelectionHandlers: function () {
            // card click on option
            $(document)
                .off('click.iyzico', '.iyzico-installment-option')
                .on('click.iyzico', '.iyzico-installment-option', function () {
                    const installmentValue = $(this).data('installment');
                    const $radioInput = $(this).find('input[type="radio"]');
                    $('input[name="installmentRadio"]').prop('checked', false);
                    $radioInput.prop('checked', true);
                    $('input[name="selectedInstallment"]').val(installmentValue);
                    $('.iyzico-installment-option').removeClass('bg-light');
                    $(this).addClass('bg-light');
                });

            // direct radio change
            $(document)
                .off('change.iyzico', 'input[name="installmentRadio"]')
                .on('change.iyzico', 'input[name="installmentRadio"]', function () {
                    const installmentValue = $(this).val();
                    $('input[name="selectedInstallment"]').val(installmentValue);
                    $('.iyzico-installment-option').removeClass('bg-light');
                    $(this).closest('.iyzico-installment-option').addClass('bg-light');
                });
        },

        /**
         * Installments
         */
        /**
         * Populate the installment options in the UI.
         * @param {Array} installmentData - Array of installment options.
         */
        _populateInstallmentOptions: function (installmentData) {
            const $container = $('#installment-options-container');

            $container.find('.iyzico-installment-option').remove();

            installmentData.forEach((option, index) => {
                const isLast = index === installmentData.length - 1;
                const borderClass = isLast ? '' : 'border-bottom';

                const $installmentOption = $(`
                    <div class="iyzico-installment-option border ${borderClass}" data-installment="${option.installmentNumber}">
                        <div class="d-flex align-items-center py-1 px-2">
                            <div class="form-check me-3">
                                <input class="form-check-input" type="radio" name="installmentRadio"
                                       value="${option.installmentNumber}" id="installment${option.installmentNumber}"
                                       ${option.installmentNumber === 1 ? 'checked="checked"' : ''} />
                                <label class="form-check-label" for="installment${option.installmentNumber}"></label>
                            </div>
                            <div class="flex-grow-1">
                                <div class="d-flex justify-content-between align-items-center">
                                    <div>
                                        <h6 class="mb-1 ${option.installmentNumber === 1 ? 'fw-bold' : ''}">
                                            ${option.installmentNumber === 1 ? _t('Single Payment') : sprintf(_t('%s Months'), option.installmentNumber)}
                                        </h6>
                                        <small class="${option.installmentNumber === 1 ? 'text-success' : 'text-muted'}">
                                            ${option.installmentNumber === 1
                        ? `<i class="fa fa-check-circle me-1"></i>${_t('No commission')}`
                        : sprintf(_t('Monthly amount: %s'), option.monthlyPrice)
                    }
                                        </small>
                                    </div>
                                    <div class="text-end">
                                        <div class="fw-bold ${option.installmentNumber === 1 ? 'text-primary' : ''} installment-amount"
                                             data-amount="${option.totalPrice}">${option.totalPrice}</div>
                                        ${option.additionalFee ? `<small>+${option.additionalFee}</small>` : ''}
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                `);

                $container.append($installmentOption);
            });
        },


        /**
         * Load installment options for the given card number.
         * @param {string} cardNumber - The card number.
         * @returns {Promise} Promise resolving when the request is complete.
         */
        _loadInstallmentOptions: function (cardNumber) {
            if ((cardNumber || '').length < 8) return;

            const $section = $('#iyzico-installments');
            const $container = $('#installment-options-container');

            if ($section.hasClass('d-none') === false && this._lastCardNumber === cardNumber) {
                // already loaded for this card
                $container.find('.iyzico-loading').remove();
                return;
            }

            this._lastCardNumber = cardNumber;

            // set title and subtitle
            $('#installment-title').text(_t('Installment Options'));
            $('#installment-subtitle').text(_t('Choose the installment option that suits your card'));

            // real call
            return rpc.query({
                route: '/payment/iyzico/installment_options',
                params: {
                    card_number: cardNumber,
                    amount: parseFloat(this.txContext.amount),
                    access_token: this.txContext.accessToken,
                    partner_id: this.txContext.partnerId,
                    provider_id: parseInt($("#iyzico-form [name='iyzico_provider_id']").val(), 10),

                },
            }).then(data => {
                $container.find('.iyzico-loading').remove();
                if (data.status === 'success' && (data.installment_options || []).length > 0) {
                    this._populateInstallmentOptions(data.installment_options);
                    $section.removeClass('d-none');
                } else {
                    $container.append(`
                        <div class="alert alert-warning text-center m-3">
                            ${_t('Unable to load installment options. Please try again.')}
                        </div>
                    `);
                }
            }).guardedCatch(() => {
                $container.find('.iyzico-loading').remove();
                $container.append(`
                    <div class="alert alert-warning text-center m-3">
                        ${_t('Unable to load installment options. Please try again.')}
                    </div>
                `);
            });
        },

        /**
         * Payments
         */
        /**
         * Process a direct payment for Iyzico.
         * @param {string} code - The provider code.
         * @param {number} providerId - The provider ID.
         * @param {Object} processingValues - The processing values.
         * @returns {Promise} Promise resolving with payment response.
         */
        _processDirectPayment: function (code, providerId, processingValues) {
            if (code !== 'iyzico_altinkaya') {
                return this._super(...arguments);
            }

            const selectedInstallment = $('input[name="selectedInstallment"]').val() || '1';

            return this._rpc({
                route: '/payment/iyzico/payments',
                params: {
                    provider_id: providerId,
                    reference: processingValues.reference,
                    access_token: processingValues.access_token,
                    installment: selectedInstallment,
                    force_3ds: $("#iyzico-form [name='iyzico_force_3ds']")[0].checked,
                    card_args: {
                        card_name: $("#iyzico-form [name='cardName']").val(),
                        card_number: $("#iyzico-form [name='cardNumber']").val(),
                        card_valid_month: $("#iyzico-form [name='validMonth']").val(),
                        card_valid_year: $("#iyzico-form [name='validYear']").val(),
                        card_cvv: $("#iyzico-form [name='cardCVV']").val(),
                    },
                },
            }).then(paymentResponse => {
                if (paymentResponse.status === 'success') {
                    // paymentResponse may be a base64-encoded script string in your flow.
                    // If it's the whole object, adapt to paymentResponse.script_b64.
                    if (paymentResponse.payment_method === '3ds') {
                        const codeStr = this._base64ToUtf8(paymentResponse.encoded_form);
                        // https://stackoverflow.com/questions/1236360/how-do-i-replace-the-entire-html-node-using-jquery
                        let redirectPage = document.open("text/html", "replace");
                        redirectPage.write(codeStr);
                        redirectPage.close();
                    }
                    else {
                        // non-3DS, just reload to show the updated status
                        window.location.href = this.txContext.landingRoute;
                    }
                } else if (paymentResponse.status === 'error') {
                    this._displayError(
                        _t('Payment Error'),
                        _t('We are not able to process your payment.'),
                        paymentResponse.error_message
                    );
                }
            }).guardedCatch((error) => {
                if (error && error.event) error.event.preventDefault();
                this._displayError(
                    _t('Server Error'),
                    _t('We are not able to process your payment.'),
                    error?.message?.data?.message || _t('Unexpected error')
                );
            });
        },

        /**
         * Prepare the inline form for Iyzico payments.
         * @param {string} code - The provider code.
         * @param {number} paymentOptionId - The payment option ID.
         * @param {string} flow - The payment flow.
         * @returns {Promise} Promise resolving when preparation is complete.
         */
        _prepareInlineForm: function (code, paymentOptionId, flow) {
            if (code !== 'iyzico_altinkaya') {
                return this._super(...arguments);
            }
            if (flow === 'token') return Promise.resolve();
            this._setPaymentFlow('direct');
            return Promise.resolve();
        }
    };

    checkoutForm.include(paymentiyzicoMixin);
    manageForm.include(paymentiyzicoMixin);
});
