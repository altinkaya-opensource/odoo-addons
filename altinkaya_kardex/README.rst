===============================
Altınkaya Kardex JMIF Integration
===============================

Drives Kardex vertical lift modules (VLM) from Odoo over the JMIF gateway, where
**every tray cell is a real ``stock.location``**. Native reservation, putaway and
barcode flows therefore work at cell granularity.

Concepts
========

- **stock.location.tray.type** — a ``rows × cols`` grid plus physical dimensions.
- **stock.kardex** — one machine: JMIF host/port and the ``depot / corridor /
  cabinet`` prefix of every location code. ``cabinet_no`` is the machine number
  (1–4 at Altınkaya).
- **stock.location** — setting a *Tray Type* turns a location into a tray and
  auto-generates one internal cell location per grid slot. Each cell's structured
  code ``depot-corridor-cabinet-shelf-bin`` is also its scannable **barcode**.
  ``shelf_no`` is the single human-readable shelf number: it is both the **JMIF
  carrier** the machine moves and the *shelf* part of the code.
- Flags ``is_kardex_tray`` / ``is_kardex_cell`` / ``is_kardex_root`` (stored, with
  search filters and group-by).

Operator flow
=============

The machine only **brings the tray to the opening**; the quantity is entered on
the hand terminal, not the machine screen. A pick from a Kardex cell is:

1. The operator requests the product on the terminal, which brings the cell's
   tray (**Call Kardex Trays**).
2. When the tray arrives, the operator scans the cell's location barcode, scans
   the product and enters the quantity — the normal ``qty_done`` flow.
3. The tray is sent back (**Send Trays Back**).

Each machine call blocks until the tray has physically arrived (or returned), so
the operator knows the tray is ready before scanning. No confirmed quantity comes
back from the machine — the tray only has to be brought to the opening.

Buttons: a picking that touches Kardex cells shows *Call Kardex Trays* and *Send
Trays Back*; a tray location shows *Bring Tray* and *Return Tray*.

Notes
=====

This installation of JMIF (``v1.8.46-DirectStore``) is synchronous-only and has
no callback/webhook; its async status API (``RestDispatcher``, port 8090) is
disabled. A bring/return call blocks only until the tray physically arrives or
returns — a short, bounded wait, not the operator-confirmation wait — so the
synchronous model is a good fit and the async API is not needed.
