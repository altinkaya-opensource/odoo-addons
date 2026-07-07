# Copyright 2026 Yiğit Budak, Altinkaya Enclosures
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
import logging

import requests

_logger = logging.getLogger(__name__)

# OCA task_type -> JMIF "code" (movement type, JMIF manual table 8). This DirectStore
# install only handles 0/1/2 — order-based 3/4 and inventory 5 come back as a generic
# 101. put=1 (singleIn) is confirmed against the machine; get=2 (singleOut) and bring=0
# are the documented pair — verify on the first real pick.
JMIF_OPERATION_CODES = {
    "release": "0",  # default: bring tray to opening / carrier 0 returns it
    "count": "0",  # bring the tray to the opening (tray call / browse)
    "put": "1",  # singleIn (store)
    "get": "2",  # singleOut (pick)
    "release_tray": "42",  # releaseTray (send the tray back to storage)
}

# OCA request key -> JMIF JSON field. "task_type" is handled separately above.
JMIF_FIELD_MAP = {
    "task_id": "hostId",
    "address": "addr",
    "carrier": "carrier",
    "pos_x": "pos",
    "pos_y": "depth",
    "qty": "quant",
    "info1": "order",
    "info2": "part",
    "info3": "desc",
}

# The full host telegram. ALL 17 fields must be present in the JSON or the gateway can't
# parse it and returns a generic 101 (with an empty hostId echoed back). The fields we
# don't use are still sent with safe defaults.
JMIF_FIELDS = (
    "code",
    "hostId",
    "addr",
    "carrier",
    "carrierNext",
    "pos",
    "depth",
    "quant",
    "order",
    "part",
    "desc",
    "x",
    "y",
    "height",
    "mPos",
    "mPos2",
    "shortText",
)
# Numeric telegram fields. This install rejects an empty value for them on parse
# (despite allowNaN in the spec), so they default to "0", not "".
JMIF_NUMERIC_FIELDS = (
    "carrier",
    "carrierNext",
    "pos",
    "depth",
    "quant",
    "x",
    "y",
    "height",
    "mPos",
    "mPos2",
)

# Read timeout (s) for a blocking pick/put: JMIF holds the connection open until the
# operator confirms at the machine (jmif.HS.timeout = 360 s on the server).
JMIF_BLOCKING_TIMEOUT = 360

# Read timeout (s) for a fire-and-forget tray-browse call.
# ponytail: a guess; tune to JMIF's queue-ack latency once on the real gateway.
JMIF_TRAY_CALL_TIMEOUT = 2


def _map_code(jmif_code):
    """Normalise a JMIF response code into the connector contract used by
    stock.kardex._send: 0 success, -2 lost, -3 timeout, -4 hardware, -5 cancelled
    (-1 refused is raised by request_operation on a ConnectionError)."""
    if jmif_code == "0":
        return "0"
    if jmif_code == "104":  # execution timeout
        return "-3"
    if jmif_code == "107":  # process aborted
        return "-5"
    if not jmif_code:  # empty body / lost response
        return "-2"
    return "-4"  # 101/103/106/108/301/302... machine or request error


class JmifRequest:
    """Talk to a Kardex JMIF gateway over the Simple HTTP (JSON) model.

    One synchronous POST per operation: ``{code, hostId, addr, carrier, ...}`` in,
    ``{code, hostId, addr, carrier[, quant]}`` back. The HTTP status is always 200; the
    real outcome is the body ``code`` (0 ok, >=100 error). See the JMIF API docs.
    """

    def __init__(self, ip, port, timeout=0, user=None, password=None, **options):
        self.ip = ip
        self.port = int(port)
        self.timeout = float(timeout) if timeout else 0
        self._auth = (user, password) if user else None
        self.ignore_response = options.get("ignore_response")

    def _prepare_payload(self, data):
        """Build the full 17-field JMIF telegram from a request dict.

        Every field must be present (missing ones break the parse), values are
        strings, and numeric fields default to "0" not "" (the gateway rejects
        empty numerics).
        """
        payload = dict.fromkeys(JMIF_FIELDS, "")
        payload["code"] = JMIF_OPERATION_CODES.get(data.get("task_type"), "0")
        for oca_key, jmif_key in JMIF_FIELD_MAP.items():
            value = data.get(oca_key)
            if value not in (None, ""):
                payload[jmif_key] = str(value)
        # JMIF wants an integer quantity, no decimals or thousands separators.
        if payload["quant"]:
            payload["quant"] = str(int(float(payload["quant"])))
        for field in JMIF_NUMERIC_FIELDS:
            if not payload[field]:
                payload[field] = "0"
        return payload

    def request_operation(self, data):
        """@param {dict} data: a _prepare_vlm_request() dict.
        @return {dict} normalised {code, task_id, qty}."""
        payload = self._prepare_payload(data)
        task_id = payload.get("hostId")
        url = f"http://{self.ip}:{self.port}/"
        timeout = (
            JMIF_TRAY_CALL_TIMEOUT
            if self.ignore_response
            else (self.timeout or JMIF_BLOCKING_TIMEOUT)
        )
        _logger.info("JMIF request to %s: %s", url, payload)
        try:
            response = requests.post(
                url, json=payload, auth=self._auth, timeout=timeout
            )
        except requests.exceptions.ConnectionError:
            return {"code": "-1", "task_id": task_id}
        except requests.exceptions.Timeout:
            # A tray-browse call doesn't wait for the operator; JMIF still runs it.
            return {"code": "0" if self.ignore_response else "-3", "task_id": task_id}
        return self._parse_response(response, data, task_id)

    def _parse_response(self, response, data, task_id):
        try:
            body = response.json()
        except ValueError:
            _logger.warning("JMIF non-JSON response: %s", response.text)
            return {"code": "-2", "task_id": task_id}
        _logger.info("JMIF response: %s", body)
        # qty: operator-confirmed quant if JMIF echoes it, else the requested qty.
        return {
            "code": _map_code(str(body.get("code", ""))),
            "task_id": body.get("hostId", task_id),
            "qty": body.get("quant", data.get("qty")),
        }
