from odoo.tests.common import TransactionCase


class TestSaleOrderOpportunity(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env["res.partner"].create({"name": "CRM Test Customer"})
        cls.pricelist = cls.env["product.pricelist"].create(
            {
                "name": "CRM Test Pricelist",
                "currency_id": cls.env.company.currency_id.id,
            }
        )
        cls.product = cls.env["product.product"].create(
            {
                "name": "CRM Test Service",
                "type": "service",
                "list_price": 100.0,
                "taxes_id": [(6, 0, [])],
                "supplier_taxes_id": [(6, 0, [])],
            }
        )

    def test_create_opportunity_from_quotation(self):
        order = self.env["sale.order"].create(
            {
                "partner_id": self.partner.id,
                "pricelist_id": self.pricelist.id,
                "order_line": [
                    (
                        0,
                        0,
                        {
                            "name": self.product.display_name,
                            "product_id": self.product.id,
                            "product_uom_qty": 2.0,
                            "product_uom": self.product.uom_id.id,
                            "price_unit": 100.0,
                            "tax_id": [(6, 0, [])],
                        },
                    )
                ],
            }
        )

        action = order.action_create_crm_opportunity()
        opportunity = order.opportunity_id

        self.assertTrue(opportunity)
        self.assertEqual(opportunity.type, "opportunity")
        self.assertEqual(opportunity.partner_id, order.partner_id)
        self.assertEqual(opportunity.expected_revenue, order.amount_untaxed)
        self.assertEqual(opportunity.currency_id, order.currency_id)
        self.assertEqual(action["res_id"], opportunity.id)

        order.action_create_crm_opportunity()
        self.assertEqual(order.opportunity_id, opportunity)
