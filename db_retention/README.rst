==================
Database Retention
==================

Retention rules to purge old records from any model on a schedule.

Several Odoo tables grow without bound and have no built-in retention
(``ir.logging`` is the classic example; ``queue.job`` only auto-vacuums
channels that have a matching ``queue.job.channel`` record, so jobs on
orphan channels accumulate forever). This module lets an administrator
define declarative retention rules and applies them daily.

Features
========

* One rule per model: pick the model, the date/datetime field, and the
  retention period in days.
* Optional extra domain to narrow what is deleted
  (e.g. ``[('state', 'in', ('done', 'cancelled'))]``).
* Batched, per-transaction deletes (configurable batch size) so large
  tables are cleaned without long locks or unbounded memory use.
* Daily cron applies every active rule; a failing rule is logged and
  skipped so it cannot block the others.
* ``Run Now`` and ``Dry Run`` buttons for manual / preview use.

Configuration
=============

#. Go to *Settings > Technical > Database Retention*.
#. A default rule purges ``ir.logging`` older than 30 days.
#. Add more rules as needed. Example for the OCA *queue_job* module:

   * Model: ``queue.job``
   * Date Field: ``date_done``
   * Retention Days: ``30``
   * Domain: ``[('state', 'in', ('done', 'cancelled'))]``

Notes
=====

* Deletes are executed as raw SQL (after the ORM resolves the domain to
  ids) for speed, then the ORM cache is invalidated. This relies on the
  database to handle inbound references, so it is safe for tables whose
  foreign keys are ``ON DELETE CASCADE`` or ``SET NULL`` (logs, jobs). A
  ``RESTRICT`` reference will raise rather than cascade -- intended, since
  this module is meant for high-volume technical tables, not business data.
* Rules are stored as data with ``noupdate="1"``; editing the default
  rule will not be overwritten on module upgrade.

Credits
=======

Author: Ahmet Yiğit Budak
License: AGPL-3
