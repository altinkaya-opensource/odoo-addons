from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestDHLAddress(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.turkey = cls.env.ref("base.tr")
        cls.state = cls.env["res.country.state"].create(
            {
                "name": "Test Province",
                "code": "TP",
                "country_id": cls.turkey.id,
            }
        )
        cls.district = cls.env["address.district"].create(
            {
                "name": "Test District",
                "state_id": cls.state.id,
            }
        )
        cls.carrier = cls.env["delivery.carrier"]

    def _create_partner(self, **values):
        return self.env["res.partner"].create(
            dict(
                {
                    "name": "Test Partner",
                    "street": "Test Street 1",
                    "country_id": self.turkey.id,
                },
                **values,
            )
        )

    def test_city_name_uses_city_when_set(self):
        """
        The partner city is kept when it is set.
        """
        partner = self._create_partner(state_id=self.state.id, city="Test City")

        address = self.carrier._prepare_dhl_address(partner)

        self.assertEqual(address["cityName"], "Test City")

    def test_city_name_uses_district_and_province(self):
        """
        Turkish addresses without city send the district and the province.
        """
        partner = self._create_partner(
            state_id=self.state.id, district_id=self.district.id
        )

        address = self.carrier._prepare_dhl_address(partner)

        self.assertEqual(address["cityName"], "Test District Test Province")

    def test_city_name_uses_province_without_district(self):
        """
        The province is the last fallback when there is no district.
        """
        partner = self._create_partner(state_id=self.state.id)

        address = self.carrier._prepare_dhl_address(partner)

        self.assertEqual(address["cityName"], "Test Province")
