USD dashboard measures
======================

Upgrade ``altinkaya_reports`` to 16.0.1.3.0 before selecting the new fields.
Odoo fills the stored analytic USD amount on existing entries during the upgrade.
This module does not change dashboard records.

For the ``Gider Toplamı`` tile:

* Keep model ``account.analytic.line`` and its existing domain/date filter.
* Select ``amount_usd`` (Amount (USD)), aggregation Sum.
* Keep the existing -1 multiplier.

For the ``Tedarikçi Fatura Tutarı`` tile:

* Keep model ``account.invoice.report`` and its posted supplier-invoice filter.
* Select ``price_total_incl_tax_usd`` (Total Including Taxes (USD)), aggregation Sum.
* Keep the existing -1 multiplier.
* Do not substitute ``price_total_usd``: that existing field remains untaxed.

For both tiles, use Number System ``Exact Value`` and two decimal digits.
Enable ``Show Custom Unit``, choose ``Custom`` and enter ``$`` (or ``USD``).
This avoids the existing ``Monetary`` setting's TRY currency. The new measure
performs the conversion; the unit setting only labels the result.

Analytic amounts keep their original allocation and sign. They use Odoo's
configured currency conversion at the analytic entry date and company, without
rounding each allocation. The stored value recomputes when the entry's amount,
date, currency or company changes. Correcting historical exchange rates alone
requires recomputing the stored field; this module does not change rate policy.

The tax-inclusive invoice measure converts each line's ``price_total`` using
the company-currency rate implied by its booked balance and foreign amount,
then applies the existing report currency normalization and invoice USD rate.
For a zero-subtotal line with a fixed tax, it uses the invoice currency rate.
Company-currency lines use a factor of one, including converted invoices that
retain their original foreign rate in the header.

This follows the existing untaxed USD report's valuation basis, including
custom invoice rates. It is not a separate direct conversion of the original
document total: custom-rate USD bills can differ from their original USD face
value. Existing report measures and invoice/accounting amounts are unchanged.
