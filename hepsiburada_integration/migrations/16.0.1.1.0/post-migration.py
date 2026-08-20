# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import json
import logging
from datetime import timedelta

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def _load_json(raw_data):
    try:
        return json.loads(raw_data or "{}")
    except (TypeError, ValueError):
        return {}


def _migrate_orders(env):
    cr = env.cr
    package_count = 0
    address_count = 0
    for order in env["hepsiburada.order"].search([]):
        try:
            with cr.savepoint():
                order._ensure_package_records()
                raw_data = _load_json(order.raw_data)
                raw_line_ids = {
                    str(item.get("lineItemId") or item.get("id") or "")
                    for item in raw_data.get("items", [])
                }
                if (
                    len(order.package_ids) == 1
                    and not order.package_ids.raw_data
                    and raw_line_ids
                ):
                    package = order.package_ids
                    package.raw_data = order.raw_data
                    package.line_ids.filtered(
                        lambda line: line.hb_line_item_id not in raw_line_ids
                    ).write({"package_id": False})
                    order.hb_line_item_ids.filtered(
                        lambda line: (
                            not line.package_id and line.hb_line_item_id in raw_line_ids
                        )
                    ).write({"package_id": package.id})
                order._sync_from_packages()
                package_count += len(order.package_ids)
                if raw_data.get("shippingAddressDetail"):
                    order._refresh_shipping_partner(raw_data)
                    address_count += 1
        except Exception:
            _logger.exception("Could not migrate HB order %s", order.id)
    return package_count, address_count


def _migrate_claims(env):
    cr = env.cr
    Claim = env["hepsiburada.claim"]
    claim_count = 0
    for claim in Claim.search([]):
        raw_data = _load_json(claim.raw_data)
        if not raw_data:
            continue
        try:
            with cr.savepoint():
                Claim._import_claim(claim.backend_id, raw_data)
                claim_count += 1
        except Exception:
            _logger.exception("Could not reparse HB claim %s", claim.id)
    return claim_count


def _migrate_questions(env):
    cr = env.cr
    Question = env["hepsiburada.question"]
    question_count = 0
    for question in Question.search([]):
        raw_data = _load_json(question.raw_data)
        if not raw_data:
            continue
        try:
            with cr.savepoint():
                Question._import_question(question.backend_id, raw_data)
                question._import_conversations(raw_data.get("conversations", []))
                question_count += 1
        except Exception:
            _logger.exception("Could not reparse HB question %s", question.id)
    return question_count


def _settlement_review_reason(settlement):
    if str(settlement.payment_status or "").lower() != "paid" and (
        settlement.odoo_payment_id or settlement.commission_payment_id
    ):
        return "A payment was posted before Hepsiburada marked the transaction Paid."
    if settlement.commission_payment_id:
        return (
            "Legacy commission payment has no matched supplier invoice and "
            "must be reviewed."
        )
    return False


def _migrate_settlements(env):
    cr = env.cr
    Settlement = env["hepsiburada.settlement"]
    settlement_count = 0
    for settlement in Settlement.search([]):
        raw_data = _load_json(settlement.raw_data)
        if raw_data:
            try:
                with cr.savepoint():
                    Settlement._import_settlement(settlement.backend_id, raw_data)
                    settlement_count += 1
            except Exception:
                _logger.exception("Could not reparse HB settlement %s", settlement.id)

        review_reason = _settlement_review_reason(settlement)
        if review_reason:
            settlement.write(
                {
                    "state": "error",
                    "requires_manual_review": True,
                    "review_reason": review_reason,
                    "error_message": review_reason,
                }
            )
    return settlement_count


def _reset_sync_cursors(env):
    Settlement = env["hepsiburada.settlement"]
    for backend in env["hepsiburada.backend"].search([]):
        earliest_settlement = Settlement.search(
            [
                ("backend_id", "=", backend.id),
                ("transaction_date", "!=", False),
            ],
            order="transaction_date asc",
            limit=1,
        )
        backend.write(
            {
                "last_order_sync": False,
                "last_order_sync_error": False,
                "last_settlement_sync": earliest_settlement.transaction_date
                - timedelta(days=1)
                if earliest_settlement
                else False,
                "last_settlement_sync_error": False,
                "last_question_sync_error": False,
                "last_claim_sync_error": False,
            }
        )


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    cr.execute(
        """
        UPDATE hepsiburada_question
           SET hb_status = CASE hb_status
               WHEN 'waiting_customer' THEN 'answered'
               WHEN 'closed' THEN 'auto_closed'
               WHEN 'open' THEN 'waiting_merchant'
               ELSE hb_status
           END
         WHERE hb_status IN ('waiting_customer', 'closed', 'open')
        """
    )
    package_count, address_count = _migrate_orders(env)
    claim_count = _migrate_claims(env)
    question_count = _migrate_questions(env)
    settlement_count = _migrate_settlements(env)
    _reset_sync_cursors(env)

    _logger.info(
        "Migrated HB data: %d packages, %d addresses, %d claims, "
        "%d questions, %d settlements",
        package_count,
        address_count,
        claim_count,
        question_count,
        settlement_count,
    )
