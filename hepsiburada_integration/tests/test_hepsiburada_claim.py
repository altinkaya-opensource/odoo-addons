# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from .common import HepsiburadaCommon


class TestHepsiburadaClaim(HepsiburadaCommon):
    def test_import_uses_current_claim_schema(self):
        claim = self.env["hepsiburada.claim"]._import_claim(
            self.backend,
            {
                "id": "claim-id",
                "number": "CLAIM-1",
                "claimType": "MissingInvoice",
                "status": "AwaitingPreApproval",
                "orderNumber": "ORDER-1",
                "lineItemId": "LINE-1",
                "sku": "HBSKU-1",
                "MerchantSku": "MERCHANT-1",
                "quantity": 2,
            },
        )

        self.assertEqual(claim.claim_type, "missing_invoice")
        self.assertEqual(claim.hb_status, "awaiting_pre_approval")
        self.assertEqual(claim.hb_line_item_id, "LINE-1")
        self.assertEqual(claim.hb_sku, "HBSKU-1")
        self.assertEqual(claim.merchant_sku, "MERCHANT-1")

    def test_unknown_claim_type_does_not_become_return(self):
        claim = self.env["hepsiburada.claim"]._import_claim(
            self.backend,
            {
                "number": "CLAIM-UNKNOWN",
                "claimType": "NewFutureType",
                "status": "NewFutureStatus",
            },
        )

        self.assertEqual(claim.claim_type, "unknown")
        self.assertEqual(claim.hb_status, "unknown")
