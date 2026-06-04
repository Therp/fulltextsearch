# Copyright 2025 Therp BV <https://therp.nl>.
# License AGPL-3 - See http://www.gnu.org/licenses/agpl-3.0.html
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestMailSearch(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Proxy = cls.env["fts.proxy"]
        cls.Message = cls.env["mail.message"]
        cls.Partner = cls.env["res.partner"]
        cls.partner_jan = cls.Partner.create(
            {
                "is_company": False,
                "name": "Jan Boezeroen",
                "email": "jboezeroen@example.com",
            }
        )

    def test_search_mail(self):
        """Test search posted mail."""
        self.partner_jan.message_post(
            body="Een nieuwe lente, een nieuw geluid:\n"
            "Ik wil dat dit lied klinkt als het gefluit,\n"
            "Dat ik vaak hoorde voor een zomernacht\n"
            "In een oud stadje, langs de watergracht."
        )
        records = self.Message.search([("body_tsvector", "like", "zomernacht")])
        self.assertTrue(records)
        self.assertEqual(records[0].model, self.Partner._name)
        self.assertEqual(records[0].res_id, self.partner_jan.id)
        proxy_records = self.Proxy.search(
            [
                ("res_model", "=", self.Message._name),
                ("searchstring", "=", "lente zomernacht"),
            ]
        )
        self.assertTrue(proxy_records)
        proxy = proxy_records[0]
        self.assertEqual(proxy.res_model, self.Message._name)
        message = self.Message.browse(proxy.res_id)
        self.assertEqual(message.model, self.Partner._name)
        self.assertEqual(message.res_id, self.partner_jan.id)

    def test_proxy_res_name(self):
        """Mails without a subject should get record id as res_name in fts_proxy"""
        # Mail with a subject
        msg_with_subject = self.Message.create(
            {
                "subject": "A subject",
                "body": "a body",
                "message_type": "comment",
                "model": self.Partner._name,
                "res_id": self.partner_jan.id,
            }
        )
        # Mail without a subject
        msg_without_subject = self.Message.create(
            {
                "subject": False,  # no subject
                "body": "another body",
                "message_type": "comment",
                "model": self.Partner._name,
                "res_id": self.partner_jan.id,
            }
        )
        proxy_records = self.Proxy.search(
            [
                ("res_model", "=", self.Message._name),
                ("searchstring", "=", "body"),
            ]
        )
        self.assertTrue(proxy_records)
        proxy_by_res_id = {p.res_id: p for p in proxy_records}
        # Mail with subject: res_name should be the subject
        proxy_with = proxy_by_res_id.get(msg_with_subject.id)
        self.assertEqual(proxy_with.res_name, "A subject")
        # Mail without subject: res_name should be record id
        proxy_without = proxy_by_res_id.get(msg_without_subject.id)
        self.assertEqual(proxy_without.res_name, "record %d" % msg_without_subject.id)
