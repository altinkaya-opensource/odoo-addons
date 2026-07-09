# Copyright 2026 Yiğit Budak, Altinkaya Enclosures
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
import uuid

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .jmif_request import JmifRequest


class StockKardex(models.Model):
    """A physical Kardex vertical lift, reachable through a JMIF gateway.

    Its ``location_id`` is the root stock.location of the machine; tray and cell
    locations live under it (see stock_location.py).
    """

    _name = "stock.kardex"
    _description = "Kardex Vertical Lift"

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    location_id = fields.Many2one(
        comodel_name="stock.location",
        string="Root Location",
        required=True,
        ondelete="restrict",
        help="Top stock location of the machine. Trays and cells hang under it.",
    )
    address = fields.Char(
        required=True,
        help="JMIF machine address, e.g. VLM-1",
    )
    # Location-code inputs (depot-corridor-cabinet-shelf-bin). These three identify
    # the machine; the shelf lives on the tray and the bin on the cell.
    depot_no = fields.Integer(default=2)
    corridor_no = fields.Integer(default=0)
    cabinet_no = fields.Integer(help="This machine's number, used in the cell code.")
    host = fields.Char(required=True, help="JMIF gateway host/IP")
    port = fields.Char(required=True, default="5600")
    jmif_user = fields.Char(groups="stock.group_stock_manager")
    jmif_password = fields.Char(groups="stock.group_stock_manager")
    tray_location_ids = fields.Many2many(
        comodel_name="stock.location",
        compute="_compute_tray_location_ids",
        string="Trays",
    )

    def _compute_tray_location_ids(self):
        for kardex in self:
            kardex.tray_location_ids = self.env["stock.location"].search(
                [
                    ("id", "child_of", kardex.location_id.id),
                    ("tray_type_id", "!=", False),
                ]
            )

    _sql_constraints = [
        (
            "location_id_unique",
            "unique(location_id)",
            "A Kardex is already linked to this location.",
        ),
    ]

    _CODE_FIELDS = ("depot_no", "corridor_no", "cabinet_no")

    def _sync_tray_cell_names(self):
        """Resync the codes of every cell under these machines' trays.

        Uses a flushed direct search (not the cached tray_location_ids compute) so it
        also works when trays already exist when the machine is created/reconfigured.
        """
        self.env.flush_all()
        for kardex in self.filtered("location_id"):
            self.env["stock.location"].search(
                [
                    ("id", "child_of", kardex.location_id.id),
                    ("tray_type_id", "!=", False),
                ]
            )._sync_cell_names()

    @api.model_create_multi
    def create(self, vals_list):
        kardexes = super().create(vals_list)
        kardexes._sync_tray_cell_names()
        return kardexes

    def write(self, vals):
        res = super().write(vals)
        if set(self._CODE_FIELDS) & vals.keys():
            self._sync_tray_cell_names()
        return res

    def _get_connector(self, **options):
        """Build a JMIF connector for this machine.

        The credentials are manager-only fields, so read them with elevation: a
        stock user may trigger a tray move without being able to see the secret.
        """
        self.ensure_one()
        secret = self.sudo()
        return JmifRequest(
            self.host,
            self.port,
            user=secret.jmif_user,
            password=secret.jmif_password,
            **options,
        )

    def _send(self, task_type, carrier, blocking=True, **kw):
        """Send one operation to the machine and return the connector response.

        Blocking (the default): JMIF holds the HTTP connection open until the tray
        physically arrives at (or returns from) the opening and sends the final code,
        so the operator knows the tray is ready before scanning. Callers that only
        ping the gateway pass ``blocking=False``.

        Raises a UserError on any hardware/transport failure. On success returns the
        connector dict (``{code, task_id, qty}``).
        """
        self.ensure_one()
        connector = self._get_connector(ignore_response=not blocking)
        data = {
            "task_type": task_type,
            "task_id": uuid.uuid4().hex,
            "address": self.address,
            "carrier": carrier,
            "pos_x": kw.get("pos_x", "0"),
            "pos_y": kw.get("pos_y", "0"),
            "qty": kw.get("qty", "0"),
            "info1": kw.get("info1", ""),
            "info2": kw.get("info2", ""),
            "info3": kw.get("info3", ""),
        }
        response = connector.request_operation(data)
        # Normalised connector code -> user-facing error. "0" is success.
        errors = {
            "-1": _("The connection to the Kardex was refused."),
            "-2": _(
                "The Kardex response was lost. Did the operation run at the machine? "
                "Check for inconsistencies before retrying."
            ),
            "-3": _("The Kardex operation timed out."),
            "-4": _(
                "The Kardex couldn't perform the task. Check the machine for a fault."
            ),
            "-5": _("The Kardex operation was cancelled at the machine."),
        }
        code = response.get("code", "")
        if code in errors:
            raise UserError(errors[code])
        return response

    def bring_tray(self, carrier):
        """Bring a tray (storage unit ``carrier``) to the opening.

        Blocks until the tray has physically arrived, so the caller knows it is
        ready to scan.
        """
        return self._send("count", carrier)

    def return_tray(self, carrier):
        """Send a tray (storage unit ``carrier``) back to storage.

        Blocks until the machine confirms the tray has been taken back.
        """
        return self._send("release_tray", carrier)

    def action_test_connection(self):
        """Ping the machine by requesting tray 0 (a harmless browse)."""
        self.ensure_one()
        self._send("count", "0", blocking=False)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "success",
                "message": _("Kardex %s answered.") % self.name,
                "sticky": False,
            },
        }
