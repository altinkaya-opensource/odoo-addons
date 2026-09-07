==================================
Trendyol Marketplace Integration
==================================

.. image:: https://img.shields.io/badge/licence-LGPL--3-blue.svg
   :target: https://www.gnu.org/licenses/lgpl
   :alt: License: LGPL-3

.. image:: https://img.shields.io/badge/Odoo-16.0-blueviolet.svg
   :alt: Odoo 16.0

Full integration between Odoo and `Trendyol <https://www.trendyol.com>`_ marketplace.

Features
--------

* 🛒 **Order Management** -- Automatic order import, confirmation and invoice linking
* 📦 **Product Sync** -- Stock and price updates, bulk product export
* 🔁 **Return Management** -- Automatic claim/return tracking
* 💰 **Financial Settlement** -- Settlement import and auto-reconciliation
* 💬 **Customer Q&A** -- Question-answer integration with notifications
* 🔔 **Webhook Support** -- Real-time order status notifications
* 🚚 **Cargo Mapping** -- Map Trendyol cargo providers to Odoo delivery carriers

Dependencies
------------

* `queue_job <https://github.com/OCA/queue>`_
* `delivery_state <https://github.com/OCA/delivery-carrier>`_
* `delivery_integration_base <https://github.com/altinkaya-opensource/odoo-addons>`_

Configuration
-------------

1. Create a new backend from **Trendyol > Backends**
2. Enter your **Seller ID**, **API Key** and **API Secret** from Trendyol Seller Panel
3. Configure warehouse, pricelist and sales team mappings
4. Set up cargo provider mappings in the **Cargo Mapping** tab
5. Verify the connection with **Test Connection**

Commission invoice matching
---------------------------

Upgrade the module to ``16.0.1.2.0`` to enable invoice-specific commission
matching. ``commissionInvoiceSerialNumber`` is extracted from the API payload,
including previously saved raw data. A later nonempty reference refreshes an
existing settlement without rewriting its posted financial amounts.

Trendyol commission payments are excluded from the generic invoice-centric
auto-reconciler, including its single-partner wizard entry point. New commission
payments remain posted and open until every charged settlement row associated
with the payment identifies the same vendor document. Only the matching posted
DSM bill (or vendor credit note for an inbound commission refund), in the same
company and currency, may be reconciled. Supplier, amount, payable-account and
remaining-balance checks are required. Multiple references, duplicate documents
or an existing reconciliation to another document require review.

Customer payment reconciliation continues independently. The settlement's
**Commission Matching** tab shows the API reference, target vendor document,
matching state and waiting/review reason. **Match Commission Invoice** retries
matching without creating another payment. Several order commissions may pay
the same vendor invoice; that invoice can remain partially unpaid until all
of its commissions are matched.

When automatic settlement reconciliation is enabled, the normal import retries
open commission payments created by this new flow. Its date window revisits
transactions whose commission reference is still missing. Missing references
or bills never fall back to matching the oldest open invoice.

Historical payments are excluded from generic matching but are not enrolled in
automatic invoice-specific matching. No migration removes their reconciliations
or recreates their payments. Correcting historical allocations requires a
separately reviewed list and accounting checks; do not bulk-unreconcile them.

The reference is documented in the `Trendyol domestic finance API
<https://developers.trendyol.com/docs/cari-hesap-ekstresi-entegrasyonu>`_.

Authors
-------

* `Yigit Budak <https://github.com/yibudak>`_ @ `Altinkaya Enclosures <https://www.altinkaya.com.tr>`_
