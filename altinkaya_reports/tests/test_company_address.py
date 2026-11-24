from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestCompanyAddress(TransactionCase):
    """The statement and payment receipt headers print the company's address.

    They used to print the old Ostim address written into the templates, so a
    move left every statement sent to customers and suppliers out of date.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.write(
            {
                "street": "Test Street 7",
                "street2": False,
                "zip": "06999",
                "city": "Test City",
                "phone": "+90 312 000 0000",
            }
        )
        cls.partner = cls.env["res.partner"].create({"name": "Address Test Partner"})

    def _statement_html(self, lang):
        wizard = (
            self.env["partner.statement.wizard"]
            .with_context(active_ids=self.partner.ids, wizard_lang=lang)
            .create({"partner_id": self.partner.id})
        )
        context = wizard._get_report_context()
        report_name = "altinkaya_reports.partner_statement_altinkaya"
        if lang == "en_US":
            report_name += "_en"
        html, _type = (
            self.env["ir.actions.report"]
            .with_context(**context)
            ._render_qweb_html(
                report_name,
                self.partner.ids,
                data={
                    "date_start": context["date_start"],
                    "date_end": context["date_end"],
                    "lang": context["lang"],
                },
            )
        )
        return html.decode()

    def _assert_company_address(self, html):
        self.assertIn("Test Street 7", html)
        self.assertIn("06999 Test City", html)
        self.assertNotIn("1231. Cd.", html)
        self.assertNotIn("Yenimahalle", html)

    def test_turkish_statement(self):
        """The Turkish footer also printed a stored translation that still
        named the fax and the old İvedik tax office."""
        html = self._statement_html("tr_TR")
        self._assert_company_address(html)
        self.assertNotIn("Faks", html)
        self.assertNotIn("İvedik", html)
        self.assertIn(self.company.phone, html)

    def test_english_statement(self):
        html = self._statement_html("en_US")
        self._assert_company_address(html)
        self.assertNotIn("Fax:", html)

    def test_payment_receipt(self):
        journal = self.env["account.journal"].search(
            [("type", "=", "bank"), ("company_id", "=", self.company.id)], limit=1
        )
        payment = self.env["account.payment"].create(
            {
                "payment_type": "inbound",
                "partner_type": "customer",
                "partner_id": self.partner.id,
                "amount": 10.0,
                "journal_id": journal.id,
            }
        )
        html, _type = self.env["ir.actions.report"]._render_qweb_html(
            "account.action_report_payment_receipt", payment.ids
        )
        self._assert_company_address(html.decode())
