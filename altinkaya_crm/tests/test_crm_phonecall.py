from odoo.tests.common import TransactionCase


class TestCRMPhonecall(TransactionCase):
    def test_scheduling_a_call_fills_in_the_activity_type(self):
        """Guard against a NOT NULL violation when scheduling another call."""
        activity_type = self.env.ref("mail.mail_activity_data_call")
        source = self.env["crm.phonecall"].create(
            {
                "name": "Source call",
                "activity_type_id": activity_type.id,
            }
        )

        vals = source.get_values_schedule_another_phonecall({"name": "Follow-up call"})
        self.assertNotIn(
            "activity_type_id",
            vals,
            "crm_phonecall's wizard omits activity_type_id, so the default keeps "
            "the NOT NULL constraint from raising an error at the user.",
        )

        phonecall = self.env["crm.phonecall"].create(vals)
        self.assertEqual(phonecall.activity_type_id, activity_type)
