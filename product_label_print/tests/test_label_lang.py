from unittest.mock import patch

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestLabelLanguage(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["res.lang"]._activate_lang("tr_TR")
        cls.unit = cls.env.ref("uom.product_uom_unit")
        cls.unit.with_context(lang="en_US").name = "Units"
        cls.unit.with_context(lang="tr_TR").name = "Adet"
        cls.product = cls.env["product.product"].create(
            {
                "name": "Label language enclosure",
                "type": "product",
                "detailed_type": "product",
                "default_code": "LABEL-LANG",
                "uom_id": cls.unit.id,
                "uom_po_id": cls.unit.id,
            }
        )
        cls.product.with_context(lang="tr_TR").name = "Etiket dili kutusu"
        server = cls.env["printing.server"].create({"name": "Label Lang Server"})
        cls.env.user.context_def_label_printer = cls.env["printing.printer"].create(
            {
                "name": "GODEX",
                "server_id": server.id,
                "system_name": "label_lang_godex",
                "type": "GODEX",
            }
        )

    def _wizard(self, lang):
        return (
            self.env["print.pack.barcode.wiz"]
            .with_context(
                active_model="product.product", active_id=self.product.id, lang=lang
            )
            .create({})
        )

    def _printed(self, wizard):
        with patch.object(
            type(self.env["printing.printer"]),
            "print_document",
            autospec=True,
            return_value=True,
        ) as send:
            wizard.print_label()
        return send.call_args.kwargs["content"]

    def test_default_follows_user_language(self):
        wizard = self._wizard("tr_TR")
        self.assertEqual(wizard.lang, "tr_TR")
        self.assertEqual(wizard.single_label_name, "Etiket dili kutusu")
        self.assertEqual(self._wizard("de_DE").lang, "en_US")

    def test_switching_language_rewrites_names_and_unit(self):
        wizard = self._wizard("tr_TR")
        wizard.write({"lang": "en_US", "single_label_pieces_in_pack": 5})
        self.assertEqual(wizard.single_label_name, "Label language enclosure")
        self.assertEqual(wizard.single_label_nameL1, "Label language enclosure")
        payload = self._printed(wizard)
        self.assertIn(b"Label language enclosure", payload)
        self.assertIn(b"5 Units", payload)
        self.assertNotIn(b"Adet", payload)

        wizard = self._wizard("en_US")
        wizard.write({"lang": "tr_TR", "single_label_pieces_in_pack": 5})
        payload = self._printed(wizard)
        self.assertIn(b"Etiket dili kutusu", payload)
        self.assertIn(b"5 Adet", payload)
