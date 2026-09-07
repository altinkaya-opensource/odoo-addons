=====================================
Hepsiburada Marketplace Integration
=====================================

.. image:: https://img.shields.io/badge/licence-LGPL--3-blue.svg
   :target: https://www.gnu.org/licenses/lgpl
   :alt: License: LGPL-3

.. image:: https://img.shields.io/badge/Odoo-16.0-blueviolet.svg
   :alt: Odoo 16.0

Full integration between Odoo and `Hepsiburada <https://www.hepsiburada.com>`_ marketplace.

Features
--------

* Order Management -- Automatic order import, confirmation and invoice linking
* Return / Claim Management -- Automatic claim tracking
* Financial Settlement -- Settlement import and auto-reconciliation
* Customer Q&A -- Question-answer integration
* Cargo Mapping -- Map Hepsiburada cargo providers to Odoo delivery carriers
* Shipping Labels -- Automatic label (Ortak Barkod) fetching and printing

Hepsiburada Cargo Firms
------------------------

The following cargo firm names are used by Hepsiburada in the ``cargoCompany``
field of order/package data. Use these exact names when configuring the
**Cargo Mapping** tab on the backend:

* Aras Kargo
* Borusan Lojistik
* Ceva Lojistik
* DHL E-commerce
* HepsiJet
* hepsiJET XL
* Horoz Lojistik
* Kolay Gelsin
* MNG Kargo
* PTT Kargo
* Sürat Kargo
* UPS
* Yurtiçi Kargo

Dependencies
------------

* `queue_job <https://github.com/OCA/queue>`_
* `delivery_state <https://github.com/OCA/delivery-carrier>`_
* `delivery_integration_base <https://github.com/altinkaya-opensource/odoo-addons>`_

Configuration
-------------

1. Create a new backend from **Hepsiburada > Backends**
2. Enter your **Merchant ID**, **API Username** and **API Password**
3. Configure warehouse, pricelist and sales team mappings
4. Set up cargo provider mappings in the **Cargo Mapping** tab
5. Verify the connection with **Test Connection**

Order webhooks
--------------

Upgrade the module, then open the backend's **Webhooks** tab as a Hepsiburada
manager. Generate dedicated webhook credentials and share the **Webhook Base
URL**, username and password with Hepsiburada through their integration onboarding
process. First complete their test-environment checks, then arrange production
registration and enable webhooks on the corresponding backend. Generating new
credentials replaces the previous credentials; the outbound API credentials are
separate.

The base URL is ``https://your-odoo-host/hb/wh/<backend_id>``. It must reach the
correct Odoo database. Hepsiburada calls these paths beneath it using Basic Auth:

* ``POST /orders`` and ``POST /packages`` return HTTP 201.
* ``PUT /packages/<package_number>/intransit``, ``/deliver``, ``/undeliver`` and
  ``/unpack`` return HTTP 204.
* ``PUT /lineitems/<line_item_id>/cancel`` returns HTTP 204.
* ``PUT /orders/<order_number>/shippingaddress`` returns HTTP 204.

Notifications enqueue a refresh of the current Hepsiburada API data. Pending
refresh jobs are coalesced per backend; the request body and credentials are not
stored in job arguments. Replayed notifications fetch current state instead of
applying old snapshots. Unpacked packages retain their history but release their
active line mappings so replacement packages can be created. Monitor failures in
the job queue and the backend's synchronization error field.

Keep the existing 15-minute polling enabled as a fallback. Hepsiburada does not
echo actions performed through its API back as webhooks. Enabling the receiver
does not register it with Hepsiburada automatically.

Official contract: `Siparis Webhook Modeli
<https://developers.hepsiburada.com/tr/companies/hepsiburada?guide=siparis-webhook-modeli&product=siparis-olusturma-entegrasyonu&view=guide>`_.

Authors
-------

* `Yigit Budak <https://github.com/yibudak>`_ @ `Altinkaya Enclosures <https://www.altinkaya.com.tr>`_
