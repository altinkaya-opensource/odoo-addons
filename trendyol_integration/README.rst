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

Authors
-------

* `Yigit Budak <https://github.com/yibudak>`_ @ `Altinkaya Enclosures <https://www.altinkaya.com.tr>`_
